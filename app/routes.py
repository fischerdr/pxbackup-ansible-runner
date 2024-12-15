"""API routes and handlers."""

import asyncio
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional, Tuple, Union

import aiohttp
import ansible.inventory
import ansible.playbook
import hvac
import requests
from flask import Blueprint, current_app, g, jsonify, request
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from requests.exceptions import RequestException

from .auth import auth_manager
from .models import AuditLog, Cluster, PlaybookExecution, db
from .utils.config import Config
from .utils.exceptions import (
    APIError,
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from .utils.monitoring import (
    record_vault_operation,
    track_playbook_execution,
    track_request_metrics,
)
from .utils.validation import (
    ClusterStatusResponse,
    CreateClusterRequest,
    UpdateServiceAccountRequest,
)

bp = Blueprint("api", __name__)

# Initialize extensions
config = Config.from_env()
cache = Cache(config={"CACHE_TYPE": config.CACHE_TYPE})
limiter = Limiter(key_func=get_remote_address, default_limits=[config.RATE_LIMIT_DEFAULT])

# Initialize Vault client
vault_client = hvac.Client(url=config.VAULT_ADDR, token=config.VAULT_TOKEN)


class AuthProvider:
    """
    Abstract base class for authentication providers.

    This class provides a factory method to create instances of concrete
    authentication providers based on the configured provider type.
    """

    @staticmethod
    def create_provider(provider_type: str):
        """
        Create an instance of a concrete authentication provider.

        Args:
            provider_type: The type of authentication provider to create.

        Returns:
            AuthProvider: An instance of the specified authentication provider.

        Raises:
            ValueError: If the provider type is not supported.
        """
        if provider_type.lower() == "okta":
            return OktaAuthProvider()
        elif provider_type.lower() == "keycloak":
            return KeycloakAuthProvider()
        raise ValueError(f"Unsupported auth provider: {provider_type}")

    async def verify_token(self, token: str) -> dict:
        """
        Verify a JWT token.

        Args:
            token: The JWT token to verify.

        Returns:
            dict: The decoded token claims.

        Raises:
            NotImplementedError: This method must be implemented by concrete providers.
        """
        raise NotImplementedError()


class OktaAuthProvider(AuthProvider):
    """
    Okta-specific authentication provider.

    This provider implements token verification using Okta's JWT verification
    functionality. It uses the configured Okta issuer and client ID to
    initialize the connection.
    """

    async def verify_token(self, token: str) -> dict:
        """
        Verify and decode an Okta JWT token.

        Args:
            token: The JWT token to verify.

        Returns:
            dict: The decoded token claims.

        Raises:
            AuthenticationError: If token verification fails.
        """
        jwt_verifier = JWTVerifier(
            issuer=current_app.config["OKTA_ISSUER"],
            client_id=current_app.config["OKTA_CLIENT_ID"],
        )
        return await jwt_verifier.verify_access_token(token)


class KeycloakAuthProvider(AuthProvider):
    """
    Keycloak-specific authentication provider.

    This provider implements token verification using Keycloak's OpenID Connect
    functionality. It uses the configured Keycloak server URL, client ID, realm
    name, and client secret to initialize the connection.
    """

    def __init__(self):
        """Initialize Keycloak OpenID client with configuration from app config."""
        self.keycloak_openid = KeycloakOpenID(
            server_url=current_app.config["KEYCLOAK_URL"],
            client_id=current_app.config["KEYCLOAK_CLIENT_ID"],
            realm_name=current_app.config["KEYCLOAK_REALM"],
            client_secret_key=current_app.config["KEYCLOAK_CLIENT_SECRET"],
        )

    async def verify_token(self, token: str) -> dict:
        """
        Verify and decode a Keycloak JWT token.

        Args:
            token: The JWT token to verify.

        Returns:
            dict: The decoded token claims.

        Raises:
            AuthenticationError: If token verification fails.
        """
        return self.keycloak_openid.decode_token(
            token,
            key=self.keycloak_openid.public_key(),
            options={
                "verify_signature": True,
                "verify_aud": True,
            },
        )


def verify_token(f):
    """
    Verify JWT token from request.

    This decorator checks for the presence of a JWT token in the Authorization
    header, verifies its validity using the configured authentication provider,
    and extracts the user ID from the token claims.

    Args:
        f: The function to decorate.

    Returns:
        A decorated function that verifies the JWT token before calling the
        original function.
    """

    @wraps(f)
    async def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise AuthenticationError("No token provided")

        try:
            token = auth_header.split(" ")[1]
            provider_type = current_app.config["AUTH_PROVIDER"]
            auth_provider = AuthProvider.create_provider(provider_type)
            claims = await auth_provider.verify_token(token)

            # Both Okta and Keycloak use 'sub' for user ID
            g.user_id = claims.get("sub")
            if not g.user_id:
                raise AuthenticationError("Token does not contain user ID")

            return await f(*args, **kwargs)
        except Exception as e:
            raise AuthenticationError(str(e))

    return decorated_function


@bp.errorhandler(APIError)
def handle_api_error(error):
    """
    Handle custom API errors.

    This function returns a JSON response with the error message and code.

    Args:
        error: The API error to handle.

    Returns:
        A JSON response with the error message and code.
    """
    response = {"error": error.message, "error_code": error.error_code}
    return jsonify(response), error.status_code


async def log_request(user_id: str, action: str, details: str, status: str) -> None:
    """
    Log an API request asynchronously.

    Args:
        user_id: The ID of the user making the request.
        action: The action being performed.
        details: Additional details about the request.
        status: The status of the request.
    """
    log = AuditLog(user_id=user_id, action=action, details=details, status=status)
    db.session.add(log)
    await db.session.commit()


async def run_playbook_async(playbook_path: str, extra_vars: Dict[str, Any]) -> subprocess.Popen:
    """
    Run an Ansible playbook asynchronously.

    Args:
        playbook_path: The path to the playbook.
        extra_vars: Additional variables to pass to the playbook.

    Returns:
        subprocess.Popen: The running playbook process.
    """
    cmd = ["ansible-playbook", playbook_path]
    for key, value in extra_vars.items():
        cmd.extend(["-e", f"{key}={shlex.quote(str(value))}"])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )

    return process


@bp.route("/api/v1/clusters", methods=["POST"])
@limiter.limit("10 per minute")
@track_request_metrics()
@auth_manager.verify_token
async def create_new_cluster():
    """
    Create a new cluster entry in PX-Backup.

    This endpoint creates a new cluster record in the database and runs the
    create_cluster playbook to provision the cluster.

    Returns:
        A JSON response with the created cluster ID and status.
    """
    try:
        # Validate request
        data = CreateClusterRequest(**request.json)

        # Check if cluster exists in database
        existing = await Cluster.query.filter_by(cluster_name=data.name).first()
        if existing:
            if not data.force:
                raise ResourceNotFoundError(
                    f"Cluster {data.name} already exists. Use force=true to recreate"
                )
            # If force=true, delete existing cluster
            current_app.logger.warning(f"Force recreating existing cluster {data.name}")
            # Delete associated playbook executions
            await PlaybookExecution.query.filter_by(cluster_id=existing.id).delete()
            await db.session.delete(existing)
            await db.session.commit()

        # Check if cluster exists in inventory (required)
        inventory_url = current_app.config["INVENTORY_API_URL"]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{inventory_url}/clusters/{data.name}",
                    timeout=30,  # 30 second timeout
                ) as response:
                    if response.status == 404:
                        raise ResourceNotFoundError(f"Cluster {data.name} not found in inventory")
                    elif response.status != 200:
                        raise ExternalServiceError(
                            f"Inventory API returned status {response.status}",
                            "inventory",
                        )
                    inventory_data = await response.json()
        except aiohttp.ClientError as e:
            raise ExternalServiceError(str(e), "inventory")
        except asyncio.TimeoutError:
            raise ExternalServiceError("Inventory API request timed out", "inventory")

        # Get kubeconfig based on provided source
        if data.kubeconfig_vault_path:
            start_time = time.time()
            try:
                vault_response = await vault_client.secrets.kv.v2.read_secret_version(
                    path=data.kubeconfig_vault_path,
                    mount_point=os.environ.get("VAULT_NAMESPACE", "default"),
                )
                await record_vault_operation("read_secret", start_time, True)
                kubeconfig = vault_response["data"]["data"].get("kubeconfig")
                if not kubeconfig:
                    raise ValidationError(
                        f"No kubeconfig found at Vault path: {data.kubeconfig_vault_path}"
                    )
            except Exception as e:
                await record_vault_operation("read_secret", start_time, False)
                raise ExternalServiceError(str(e), "vault")
        else:
            kubeconfig = data.kubeconfig

        # Create cluster record
        cluster = Cluster(
            cluster_name=data.name,
            service_account=data.service_account,
            namespace=data.namespace,
            status="creating",
        )
        db.session.add(cluster)
        await db.session.commit()

        # Run playbook
        playbook_path = os.path.join(current_app.config["PLAYBOOK_DIR"], "create_cluster.yml")

        # Add kubeconfig and inventory data to extra vars
        extra_vars = {
            "cluster_name": data.name,
            "service_account": data.service_account,
            "namespace": data.namespace,
            "kubeconfig": kubeconfig,
            "force": data.force,
            "overwrite": data.force,  # Set overwrite to match force flag
            "inventory_id": inventory_data.get("id"),  # Pass inventory data to playbook
            "inventory_metadata": inventory_data.get(
                "metadata", {}
            ),  # Pass any additional metadata
        }

        process = await run_playbook_async(playbook_path, extra_vars)

        # Create playbook execution record
        execution = PlaybookExecution(
            playbook_name="create_cluster.yml", status="running", cluster_id=cluster.id
        )
        db.session.add(execution)
        await db.session.commit()

        # Log the request
        action_details = f"Created cluster {data.name}"
        if data.force:
            action_details += " (force=true)"
        await log_request(g.user_id, "create_cluster", action_details, "success")

        # Return response in documented format
        return (
            jsonify(
                {
                    "id": cluster.id,
                    "name": cluster.cluster_name,
                    "status": cluster.status,
                    "created_at": cluster.created_at.isoformat(),
                    "updated_at": cluster.updated_at.isoformat(),
                }
            ),
            201,
        )

    except Exception as e:
        await log_request(
            g.user_id, "create_cluster", f"Failed to create cluster: {str(e)}", "error"
        )
        raise


@bp.route("/update_service_account", methods=["POST"])
@limiter.limit("10 per minute")
@track_request_metrics()
@auth_manager.verify_token
async def update_service_account():
    """
    Update service account for a Kubernetes cluster.

    This endpoint updates the service account for a cluster and runs the
    update_service_account playbook to apply the changes.

    Returns:
        A JSON response with a message and the execution ID.
    """
    try:
        # Validate request
        data = UpdateServiceAccountRequest(**request.json)

        # Check if cluster exists
        cluster = await Cluster.query.filter_by(cluster_name=data.cluster_name).first()
        if not cluster:
            raise ResourceNotFoundError(f"Cluster {data.cluster_name} not found")

        # Get Vault token
        start_time = time.time()
        try:
            vault_response = await vault_client.secrets.kv.v2.read_secret_version(
                path="kubernetes/cluster-config",
                mount_point=os.environ.get("VAULT_NAMESPACE", "default"),
            )
            await record_vault_operation("read_secret", start_time, True)
            vault_token = vault_client.token
        except Exception as e:
            await record_vault_operation("read_secret", start_time, False)
            raise ExternalServiceError(str(e), "vault")

        # Update service account
        cluster.service_account = data.service_account
        await db.session.commit()

        # Run playbook
        playbook_path = os.path.join(
            current_app.config["PLAYBOOK_DIR"], "update_service_account.yml"
        )

        process = await run_playbook_async(
            playbook_path,
            {
                "cluster_name": data.cluster_name,
                "service_account": data.service_account,
                "overwrite": True,  # Always overwrite when updating service account
                "vault_token": vault_token,
            },
        )

        # Create playbook execution record
        execution = PlaybookExecution(
            playbook_name="update_service_account.yml",
            status="running",
            cluster_id=cluster.id,
        )
        db.session.add(execution)
        await db.session.commit()

        # Log the request
        await log_request(
            g.user_id,
            "update_service_account",
            f"Updated service account for cluster {data.cluster_name}",
            "success",
        )

        return (
            jsonify(
                {
                    "message": f"Service account update started for cluster {data.cluster_name}",
                    "execution_id": execution.id,
                }
            ),
            202,
        )

    except Exception as e:
        await log_request(
            g.user_id,
            "update_service_account",
            f"Failed to update service account: {str(e)}",
            "error",
        )
        raise


@bp.route("/check_cluster_status/<cluster_name>")
@cache.memoize(timeout=60)
@track_request_metrics()
@auth_manager.verify_token
async def check_cluster_status(cluster_name: str):
    """
    Get status of a specific cluster.

    This endpoint returns the status of a cluster, including the latest playbook
    execution status.

    Args:
        cluster_name: The name of the cluster to check.

    Returns:
        A JSON response with the cluster status.
    """
    try:
        cluster = await Cluster.query.filter_by(cluster_name=cluster_name).first()

        if not cluster:
            raise ResourceNotFoundError(f"Cluster {cluster_name} not found")

        latest_execution = (
            await PlaybookExecution.query.filter_by(cluster_id=cluster.id)
            .order_by(PlaybookExecution.started_at.desc())
            .first()
        )

        response = ClusterStatusResponse(
            name=cluster.cluster_name,
            status=cluster.status,
            created_at=cluster.created_at.isoformat(),
            updated_at=cluster.updated_at.isoformat(),
            service_account=cluster.service_account,
            playbook_status=latest_execution.status if latest_execution else None,
        )

        return jsonify(response.dict()), 200

    except Exception as e:
        await log_request(
            g.user_id,
            "check_status",
            f"Failed to check cluster status: {str(e)}",
            "error",
        )
        raise


@bp.route("/check_status")
@track_request_metrics()
@auth_manager.verify_token
async def check_status():
    """
    Get status of all clusters.

    This endpoint returns the status of all clusters, including the latest playbook
    execution status.

    Returns:
        A JSON response with the cluster statuses.
    """
    try:
        clusters = await Cluster.query.all()
        result = []
        for cluster in clusters:
            latest_execution = (
                await PlaybookExecution.query.filter_by(cluster_id=cluster.id)
                .order_by(PlaybookExecution.started_at.desc())
                .first()
            )

            result.append(
                {
                    "cluster_name": cluster.cluster_name,
                    "status": cluster.status,
                    "service_account": cluster.service_account,
                    "playbook_status": latest_execution.status if latest_execution else None,
                }
            )

        return jsonify(result), 200

    except Exception as e:
        await log_request(g.user_id, "check_status", f"Failed to check status: {str(e)}", "error")
        raise


@bp.route("/api/v1/health", methods=["GET"])
@bp.route("/health", methods=["GET"])
@cache.cached(timeout=30)  # Cache health check for 30 seconds
async def health_check():
    """
    Health check endpoint that checks all services.

    This endpoint checks the health of the database, Vault, Redis, and Keycloak
    services.

    Returns:
        A JSON response with the health status of each service.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": {"status": "unknown"},
            "vault": {"status": "unknown"},
            "redis": {"status": "unknown"},
            "keycloak": {"status": "unknown"},
        },
    }

    try:
        # Check database connection
        start_time = time.time()
        db.session.execute("SELECT 1")
        health_status["services"]["database"] = {
            "status": "healthy",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        health_status["services"]["database"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    try:
        # Check Vault connection with timeout
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{vault_client.url}/v1/sys/health", timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    health_status["services"]["vault"] = {
                        "status": "healthy",
                        "latency_ms": round((time.time() - start_time) * 1000, 2),
                    }
                else:
                    raise Exception(f"Vault returned status {response.status}")
    except Exception as e:
        health_status["services"]["vault"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    try:
        # Check Redis connection with timeout
        start_time = time.time()
        await asyncio.wait_for(cache.ping(), timeout=5.0)
        health_status["services"]["redis"] = {
            "status": "healthy",
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        health_status["services"]["redis"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    try:
        # Check Keycloak connection with timeout
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{config.KEYCLOAK_URL}/health", timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    health_status["services"]["keycloak"] = {
                        "status": "healthy",
                        "latency_ms": round((time.time() - start_time) * 1000, 2),
                    }
                else:
                    raise Exception(f"Keycloak returned status {response.status}")
    except Exception as e:
        health_status["services"]["keycloak"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


@bp.route("/api/v1/ready", methods=["GET"])
@bp.route("/ready", methods=["GET"])
async def readiness_check():
    """
    Readiness probe that checks if the application is ready to serve traffic.

    This endpoint checks the database connection to ensure the application is
    ready to serve requests.

    Returns:
        A JSON response with the readiness status.
    """
    try:
        # Only check database connection for readiness
        # This ensures the application can serve requests
        db.session.execute("SELECT 1")
        return jsonify({"status": "ready"}), 200
    except Exception as e:
        return jsonify({"status": "not_ready", "error": str(e)}), 503
