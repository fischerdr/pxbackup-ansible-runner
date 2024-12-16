"""API routes and handlers."""

import aiohttp
import asyncio
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from contextlib import contextmanager

from flask import Blueprint, current_app, g, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import ValidationError as PydanticValidationError

from . import auth_manager, db, cache
from .exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
)
from .models import Cluster, PlaybookExecution, AuditLog
from .schemas import (
    ClusterStatusResponse,
    CreateClusterRequest,
    UpdateServiceAccountRequest,
)
from .utils import vault_client
from .utils.config import Config
from .utils.monitoring import record_vault_operation, track_request_metrics

bp = Blueprint("api", __name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])


@bp.errorhandler(ValidationError)
def handle_validation_error(error):
    """Handle validation errors."""
    return jsonify({"error": str(error), "error_code": "VALIDATION_ERROR"}), 400


@bp.errorhandler(PydanticValidationError)
def handle_pydantic_validation_error(error):
    """Handle Pydantic validation errors."""
    return (
        jsonify(
            {
                "error": "Invalid request data",
                "details": error.errors(),
                "error_code": "VALIDATION_ERROR",
            }
        ),
        400,
    )


@bp.errorhandler(ResourceNotFoundError)
def handle_not_found_error(error):
    """Handle resource not found errors."""
    return jsonify({"error": str(error), "error_code": "NOT_FOUND"}), 404


@bp.errorhandler(ResourceAlreadyExistsError)
def handle_already_exists_error(error):
    """Handle resource already exists errors."""
    return jsonify({"error": str(error), "error_code": "ALREADY_EXISTS"}), 409


@bp.errorhandler(ExternalServiceError)
def handle_external_service_error(error):
    """Handle external service errors."""
    return (
        jsonify(
            {"error": str(error), "service": error.service, "error_code": "EXTERNAL_SERVICE_ERROR"}
        ),
        503,
    )


@bp.errorhandler(AuthenticationError)
def handle_authentication_error(error):
    """Handle authentication errors."""
    return jsonify({"error": str(error), "error_code": "AUTHENTICATION_ERROR"}), 401


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


@contextmanager
def track_playbook_execution(playbook_name: str):
    """Track playbook execution with logging."""
    start_time = time.time()
    try:
        yield
    except Exception as e:
        current_app.logger.error(
            "Playbook execution failed",
            extra={
                "playbook": playbook_name,
                "error": str(e),
                "duration": time.time() - start_time,
            },
        )
        raise
    else:
        current_app.logger.info(
            "Playbook execution completed",
            extra={"playbook": playbook_name, "duration": time.time() - start_time},
        )


async def run_playbook_async(
    playbook_path: str, extra_vars: Dict[str, Any]
) -> Tuple[subprocess.Popen, str]:
    """
    Run an Ansible playbook asynchronously.

    Args:
        playbook_path: The path to the playbook.
        extra_vars: Additional variables to pass to the playbook.

    Returns:
        Tuple[subprocess.Popen, str]: The running playbook process and the command string.
    """
    playbook_name = os.path.basename(playbook_path)
    with track_playbook_execution(playbook_name):
        cmd = ["ansible-playbook", playbook_path]
        for key, value in extra_vars.items():
            cmd.extend(["-e", f"{key}={shlex.quote(str(value))}"])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        # Return both process and command string for logging
        return process, " ".join(cmd)


@bp.route("/api/v1/clusters", methods=["POST"])
@limiter.limit("10 per minute")
@track_request_metrics()
@auth_manager.login_required
async def create_new_cluster():
    """
    Create a new cluster entry in PX-Backup.

    This endpoint creates a new cluster record in the database and runs the
    create_cluster playbook to provision the cluster. Uses Redis distributed
    locking to prevent concurrent creation of the same cluster.

    Returns:
        A JSON response with the created cluster ID and status.
    """
    try:
        # Validate request
        data = CreateClusterRequest(**request.json)

        # Create Redis lock key
        lock_key = f"cluster_creation:{data.name}"

        # Try to acquire lock with 10 second timeout
        lock = cache.redis.lock(lock_key, timeout=600)  # 10 minute timeout
        if not await lock.acquire(blocking=True, blocking_timeout=10):
            raise ValidationError(
                f"Another cluster creation for {data.name} is in progress. Please wait."
            )

        try:
            # Check if cluster exists in database
            existing = await Cluster.query.filter_by(cluster_name=data.name).first()
            if existing:
                if not data.force:
                    raise ResourceAlreadyExistsError(
                        f"Cluster {data.name} already exists. Use force=true to recreate"
                    )
                # If force=true, delete existing cluster and its resources
                current_app.logger.warning(f"Force recreating existing cluster {data.name}")
                async with db.session.begin_nested():
                    # Delete associated resources in a single transaction
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
                            raise ResourceNotFoundError(
                                f"Cluster {data.name} not found in inventory"
                            )
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
                # Read vault token from sidecar file
                try:
                    with open("/vault/token", "r") as f:
                        vault_token = f.read().strip()
                except Exception as e:
                    raise ExternalServiceError(f"Failed to read vault token: {str(e)}", "vault")

                # Configure vault client with token
                vault_client.client.token = vault_token

                start_time = time.time()
                try:
                    async with vault_client.client.secrets.kv.v2.read_secret_version(
                        path=data.kubeconfig_vault_path,
                        mount_point=os.environ.get("VAULT_NAMESPACE", "default"),
                    ) as response:
                        await record_vault_operation("read_secret", start_time, True)
                        vault_data = response.data.data
                        kubeconfig_base64 = vault_data.get("kubeconfig")
                        if not kubeconfig_base64:
                            raise ValidationError(
                                f"No kubeconfig found at Vault path: {data.kubeconfig_vault_path}"
                            )
                except Exception as e:
                    await record_vault_operation("read_secret", start_time, False)
                    raise ExternalServiceError(str(e), "vault")
            elif data.kubeconfig:
                kubeconfig_base64 = data.kubeconfig
            else:
                raise ValidationError("Either kubeconfig or kubeconfig_vault_path must be provided")

            # Create cluster record
            cluster = Cluster(
                cluster_name=data.name,
                service_account=data.service_account,
                namespace=data.namespace,
                status="creating",
            )
            db.session.add(cluster)
            await db.session.commit()

            # Create playbook execution record with command info
            execution = PlaybookExecution(
                playbook_name="create_cluster.yml",
                status="running",
                cluster_id=cluster.id,
                start_time=datetime.now(timezone.utc),
                extra_vars=json.dumps(
                    {
                        "cluster_name": data.name,
                        "service_account": data.service_account,
                        "namespace": data.namespace,
                        "kubeconfig_base64": kubeconfig_base64,  # Pass as base64
                        "force": data.force,
                        "overwrite": data.force,  # Set overwrite to match force flag
                        "inventory_id": inventory_data.get("id"),  # Pass inventory data to playbook
                        "inventory_metadata": inventory_data.get(
                            "metadata", {}
                        ),  # Pass any additional metadata
                    },
                    default=str,
                ),
                command="",  # Will be updated after playbook starts
                pid=None,  # Will be updated after playbook starts
                return_code=None,
            )
            db.session.add(execution)
            await db.session.commit()

            # Add kubeconfig and inventory data to extra vars
            extra_vars = {
                "cluster_name": data.name,
                "service_account": data.service_account,
                "namespace": data.namespace,
                "kubeconfig_base64": kubeconfig_base64,
                "force": data.force,
                "overwrite": data.force,  # Set overwrite to match force flag
                "inventory_id": inventory_data.get("id"),  # Pass inventory data to playbook
                "inventory_metadata": inventory_data.get(
                    "metadata", {}
                ),  # Pass any additional metadata
            }

            # Update execution record with prepared vars
            execution.extra_vars = json.dumps(extra_vars, default=str)
            await db.session.commit()

            # Run playbook
            playbook_path = os.path.join(current_app.config["PLAYBOOK_DIR"], "create_cluster.yml")

            process, cmd_str = await run_playbook_async(playbook_path, extra_vars)
            execution.command = cmd_str
            execution.pid = process.pid
            await db.session.commit()

            # Return response in documented format
            return (
                jsonify(
                    {
                        "id": cluster.id,
                        "name": cluster.cluster_name,
                        "status": cluster.status,
                        "created_at": cluster.created_at.isoformat(),
                        "updated_at": cluster.updated_at.isoformat(),
                        "playbook_execution": {
                            "id": execution.id,
                            "status": execution.status,
                            "playbook": execution.playbook_name,
                            "start_time": execution.start_time.isoformat(),
                            "extra_vars": json.loads(execution.extra_vars),
                            "command": execution.command,
                            "pid": execution.pid,
                            "return_code": execution.return_code,
                        },
                    }
                ),
                201,
            )

        except Exception as e:
            await log_request(
                g.user_id, "create_cluster", f"Failed to create cluster: {str(e)}", "error"
            )
            raise
        finally:
            # Release lock after completion or error
            await lock.release()

    except Exception as e:
        await log_request(
            g.user_id, "create_cluster", f"Failed to create cluster: {str(e)}", "error"
        )
        raise


@bp.route("/update_service_account", methods=["POST"])
@limiter.limit("10 per minute")
@track_request_metrics()
@auth_manager.login_required
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

        # Get kubeconfig based on provided source
        if data.kubeconfig_vault_path:
            # Read vault token from sidecar file
            try:
                with open("/vault/token", "r") as f:
                    vault_token = f.read().strip()
            except Exception as e:
                raise ExternalServiceError(f"Failed to read vault token: {str(e)}", "vault")

            # Configure vault client with token
            vault_client.client.token = vault_token

            start_time = time.time()
            try:
                async with vault_client.client.secrets.kv.v2.read_secret_version(
                    path=data.kubeconfig_vault_path,
                    mount_point=os.environ.get("VAULT_NAMESPACE", "default"),
                ) as response:
                    await record_vault_operation("read_secret", start_time, True)
                    vault_data = response.data.data
                    kubeconfig_base64 = vault_data.get("kubeconfig")
                    if not kubeconfig_base64:
                        raise ValidationError(
                            f"No kubeconfig found at Vault path: {data.kubeconfig_vault_path}"
                        )
            except Exception as e:
                await record_vault_operation("read_secret", start_time, False)
                raise ExternalServiceError(str(e), "vault")
        elif data.kubeconfig:
            kubeconfig_base64 = data.kubeconfig
        else:
            raise ValidationError("Either kubeconfig or kubeconfig_vault_path must be provided")

        # Update service account
        cluster.service_account = data.service_account
        await db.session.commit()

        # Create playbook execution record
        execution = PlaybookExecution(
            playbook_name="update_service_account.yml",
            status="running",
            cluster_id=cluster.id,
            start_time=datetime.now(timezone.utc),
            extra_vars=json.dumps(
                {
                    "cluster_name": data.cluster_name,
                    "service_account": data.service_account,
                    "namespace": data.namespace,
                    "kubeconfig_base64": kubeconfig_base64,  # Pass as base64
                    "overwrite": True,  # Always overwrite when updating service account
                },
                default=str,
            ),
            command="",  # Will be updated after playbook starts
            pid=None,  # Will be updated after playbook starts
            return_code=None,
        )
        db.session.add(execution)
        await db.session.commit()

        # Run playbook and update execution record
        playbook_path = os.path.join(
            current_app.config["PLAYBOOK_DIR"], "update_service_account.yml"
        )

        process, cmd_str = await run_playbook_async(
            playbook_path,
            {
                "cluster_name": data.cluster_name,
                "service_account": data.service_account,
                "namespace": data.namespace,
                "kubeconfig_base64": kubeconfig_base64,  # Pass as base64
                "overwrite": True,  # Always overwrite when updating service account
                "force": True,  # Always force when updating service account
            },
        )
        execution.command = cmd_str
        execution.pid = process.pid
        await db.session.commit()

        return (
            jsonify(
                {
                    "message": f"Service account update started for cluster {data.cluster_name}",
                    "execution_id": execution.id,
                    "playbook_execution": {
                        "id": execution.id,
                        "status": execution.status,
                        "playbook": execution.playbook_name,
                        "start_time": execution.start_time.isoformat(),
                        "extra_vars": json.loads(execution.extra_vars),
                        "cluster_id": cluster.id,
                        "command": execution.command,
                        "pid": execution.pid,
                        "return_code": execution.return_code,
                    },
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
@auth_manager.login_required
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
        if not cluster_name:
            raise ValidationError("Cluster name is required")

        cluster = await Cluster.query.filter_by(cluster_name=cluster_name).first()
        if not cluster:
            raise ResourceNotFoundError(f"Cluster {cluster_name} not found")

        # Get latest playbook execution
        latest_execution = (
            await PlaybookExecution.query.filter_by(cluster_id=cluster.id)
            .order_by(PlaybookExecution.start_time.desc())
            .first()
        )

        response = ClusterStatusResponse(
            id=cluster.id,
            name=cluster.cluster_name,
            status=cluster.status,
            created_at=cluster.created_at.isoformat(),
            updated_at=cluster.updated_at.isoformat(),
            playbook_execution=latest_execution.to_dict() if latest_execution else None,
        )

        return jsonify(response.dict()), 200

    except Exception as e:
        await log_request(
            g.user_id, "check_cluster_status", f"Failed to get cluster status: {str(e)}", "error"
        )
        raise


@bp.route("/check_status")
@track_request_metrics()
@auth_manager.login_required
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
        response = []

        for cluster in clusters:
            # Get latest playbook execution for each cluster
            latest_execution = (
                await PlaybookExecution.query.filter_by(cluster_id=cluster.id)
                .order_by(PlaybookExecution.start_time.desc())
                .first()
            )

            status = ClusterStatusResponse(
                id=cluster.id,
                name=cluster.cluster_name,
                status=cluster.status,
                created_at=cluster.created_at.isoformat(),
                updated_at=cluster.updated_at.isoformat(),
                playbook_execution=latest_execution.to_dict() if latest_execution else None,
            )
            response.append(status.dict())

        return jsonify(response), 200

    except Exception as e:
        await log_request(
            g.user_id, "check_status", f"Failed to get clusters status: {str(e)}", "error"
        )
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
                f"{vault_client.client.url}/v1/sys/health", timeout=aiohttp.ClientTimeout(total=5)
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
                f"{Config.from_env().KEYCLOAK_URL}/health", timeout=aiohttp.ClientTimeout(total=5)
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
