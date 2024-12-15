"""Authentication module for the application."""

import os
from functools import wraps
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import hvac
import jwt
import requests
from flask import current_app, g, jsonify, request
from keycloak import KeycloakOpenID
from okta_jwt_verifier import JWTVerifier
from werkzeug.exceptions import Unauthorized


class AuthProvider:
    """Abstract base class for authentication providers."""

    @staticmethod
    def create_provider(provider_type: str) -> "AuthProvider":
        """Factory method to create the appropriate auth provider."""
        if provider_type.lower() == "okta":
            return OktaAuthProvider()
        elif provider_type.lower() == "keycloak":
            return KeycloakAuthProvider()
        raise ValueError(f"Unsupported auth provider: {provider_type}")

    async def verify_token(self, token: str) -> dict:
        """Verify and decode a JWT token."""
        raise NotImplementedError()

    def get_user_info(self, token: str) -> dict:
        """Get user information from the token."""
        raise NotImplementedError()


class OktaAuthProvider(AuthProvider):
    """Okta-specific authentication provider."""

    REQUEST_TIMEOUT = 30  # seconds

    def __init__(self):
        self.issuer = current_app.config["OKTA_ISSUER"]
        self.client_id = current_app.config["OKTA_CLIENT_ID"]
        self.jwt_verifier = JWTVerifier(issuer=self.issuer, client_id=self.client_id)

    async def verify_token(self, token: str) -> dict:
        """Verify an Okta JWT token."""
        return await self.jwt_verifier.verify_access_token(token)

    def get_user_info(self, token: str) -> dict:
        """Get user information from Okta."""
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{self.issuer}/v1/userinfo", headers=headers, timeout=self.REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()


class KeycloakAuthProvider(AuthProvider):
    """Keycloak-specific authentication provider."""

    def __init__(self):
        self.keycloak_openid = KeycloakOpenID(
            server_url=current_app.config["KEYCLOAK_URL"],
            client_id=current_app.config["KEYCLOAK_CLIENT_ID"],
            realm_name=current_app.config["KEYCLOAK_REALM"],
            client_secret_key=current_app.config["KEYCLOAK_CLIENT_SECRET"],
        )

    async def verify_token(self, token: str) -> dict:
        """Verify a Keycloak JWT token."""
        return self.keycloak_openid.decode_token(
            token,
            key=self.keycloak_openid.public_key(),
            options={"verify_signature": True, "verify_aud": True},
        )

    def get_user_info(self, token: str) -> dict:
        """Get user information from Keycloak."""
        return self.keycloak_openid.userinfo(token)


class AuthManager:
    """Manages authentication and authorization."""

    def __init__(self, app=None):
        self.app = app
        self.auth_provider = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the auth manager with the Flask app."""
        self.app = app
        provider_type = app.config.get("AUTH_PROVIDER", "keycloak")
        self.auth_provider = AuthProvider.create_provider(provider_type)

        # Initialize Vault client if needed
        vault_addr = app.config.get("VAULT_ADDR")
        vault_token = app.config.get("VAULT_TOKEN")
        if vault_addr and vault_token:
            self.vault_client = hvac.Client(url=vault_addr, token=vault_token)

    def login_required(self, f):
        """Decorator to require authentication for routes."""

        @wraps(f)
        async def decorated_function(*args, **kwargs):
            try:
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    raise Unauthorized("No valid authorization header")

                token = auth_header.split(" ")[1]
                claims = await self.auth_provider.verify_token(token)

                # Store user info in Flask g object
                g.user_id = claims.get("sub")
                if not g.user_id:
                    raise Unauthorized("Token does not contain user ID")

                return await f(*args, **kwargs)
            except Exception as e:
                raise Unauthorized(str(e))

        return decorated_function

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current user."""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]
        return self.auth_provider.get_user_info(token)


# Global instance
auth_manager = AuthManager()
