"""Provide authentication functionality for the application.

This module provides a flexible authentication system that supports both Keycloak and Okta
authentication providers. The system is designed to be easily switchable between the two
providers based on configuration.

Environment Variables:
    OKTA_ISSUER: The Okta issuer URL (required for Okta)
    OKTA_CLIENT_ID: The Okta client ID (required for Okta)
    KEYCLOAK_URL: The Keycloak server URL (required for Keycloak)
    KEYCLOAK_CLIENT_ID: The Keycloak client ID (required for Keycloak)
    KEYCLOAK_REALM: The Keycloak realm name (required for Keycloak)
    KEYCLOAK_CLIENT_SECRET: The Keycloak client secret (required for Keycloak)
"""

from functools import wraps
from typing import Any, Dict, Optional

import requests
from flask import current_app, g, request
from keycloak import KeycloakOpenID
from okta_jwt_verifier import JWTVerifier
from werkzeug.exceptions import Unauthorized

from .logging_config import configure_logging


# Configure logging
logger = configure_logging()


class AuthProvider:
    """Abstract base class for authentication providers.

    This class defines the interface that all authentication providers must implement.
    It provides a factory method for creating provider instances based on configuration.

    Methods:
        create_provider: Factory method to create authentication provider instances.
        verify_token: Abstract method to verify JWT tokens.
        get_user_info: Abstract method to retrieve user information.
    """

    @staticmethod
    def create_provider(provider_type: str) -> "AuthProvider":
        """Create an authentication provider instance.

        Args:
            provider_type (str): Type of provider to create ('okta', 'keycloak', or 'mock').

        Returns:
            AuthProvider: An instance of the appropriate authentication provider.

        Raises:
            ValueError: If an invalid provider type is specified.
        """
        if provider_type == "okta":
            return OktaAuthProvider()
        elif provider_type == "keycloak":
            return KeycloakAuthProvider()
        elif provider_type == "mock":
            return MockAuthProvider()
        else:
            raise ValueError(f"Invalid auth provider type: {provider_type}")


class MockAuthProvider(AuthProvider):
    """Mock authentication provider for testing.

    This provider allows all tokens in testing environment and returns mock user info.
    """

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify a mock token.

        Args:
            token (str): The token to verify (ignored in mock provider).

        Returns:
            Dict[str, Any]: Mock token claims.
        """
        return {
            "sub": "test-user",
            "email": "test@example.com",
            "name": "Test User",
            "roles": ["admin"],
        }

    def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get mock user information.

        Args:
            token (str): The token to use (ignored in mock provider).

        Returns:
            Dict[str, Any]: Mock user information.
        """
        return {
            "id": "test-user",
            "email": "test@example.com",
            "name": "Test User",
            "roles": ["admin"],
        }


class OktaAuthProvider:
    """Okta-specific authentication provider.

    This class implements the AuthProvider interface for Okta authentication.
    It handles token verification and user information retrieval using Okta's APIs.

    Attributes:
        REQUEST_TIMEOUT (int): Timeout for HTTP requests to Okta.
        issuer (str): The Okta issuer URL.
        client_id (str): The Okta client ID.
        jwt_verifier (JWTVerifier): Instance of Okta's JWT verification utility.
    """

    REQUEST_TIMEOUT = 30

    def __init__(self):
        """Initialize the Okta auth provider with configuration from Flask app."""
        self.issuer = current_app.config["OKTA_ISSUER"]
        self.client_id = current_app.config["OKTA_CLIENT_ID"]
        self.jwt_verifier = JWTVerifier(issuer=self.issuer, client_id=self.client_id)

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify an Okta JWT token.

        Args:
            token (str): The JWT token to verify.

        Returns:
            Dict[str, Any]: The verified token claims.

        Raises:
            Unauthorized: If the token is invalid or expired.
        """
        try:
            claims = self.jwt_verifier.verify(token)
            return claims
        except Exception as e:
            logger.error("Token verification failed", error=str(e))
            raise Unauthorized("Invalid token")

    def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information from Okta.

        Args:
            token (str): The JWT token for the user.

        Returns:
            Dict[str, Any]: User profile information from Okta.

        Raises:
            Unauthorized: If the user info request fails.
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{self.issuer}/v1/userinfo",
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Failed to get user info", error=str(e))
            raise Unauthorized("Failed to get user info")


class KeycloakAuthProvider:
    """Keycloak-specific authentication provider.

    This class implements the AuthProvider interface for Keycloak authentication.
    It handles token verification and user information retrieval using Keycloak's APIs.

    Attributes:
        keycloak_openid (KeycloakOpenID): Instance of Keycloak's OpenID client.
    """

    def __init__(self):
        """Initialize the Keycloak auth provider with configuration from Flask app."""
        self.keycloak_openid = KeycloakOpenID(
            server_url=current_app.config["KEYCLOAK_URL"],
            client_id=current_app.config["KEYCLOAK_CLIENT_ID"],
            realm_name=current_app.config["KEYCLOAK_REALM"],
            client_secret_key=current_app.config["KEYCLOAK_CLIENT_SECRET"],
        )

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify a Keycloak JWT token.

        Args:
            token (str): The JWT token to verify.

        Returns:
            Dict[str, Any]: The verified token claims.

        Raises:
            Unauthorized: If the token is invalid or expired.
        """
        try:
            return self.keycloak_openid.decode_token(
                token,
                key=self.keycloak_openid.public_key(),
                options={"verify_signature": True, "verify_aud": False},
            )
        except Exception as e:
            logger.error("Token verification failed", error=str(e))
            raise Unauthorized("Invalid token")

    def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information from Keycloak.

        Args:
            token (str): The JWT token for the user.

        Returns:
            Dict[str, Any]: User profile information from Keycloak.

        Raises:
            Unauthorized: If the user info request fails.
        """
        try:
            return self.keycloak_openid.userinfo(token)
        except Exception as e:
            logger.error("Failed to get user info", error=str(e))
            raise Unauthorized("Failed to get user info")


class AuthManager:
    """Manages authentication and authorization.

    This class provides a centralized way to handle authentication and authorization
    across the application. It supports multiple authentication providers and provides
    decorators for protecting routes.

    Attributes:
        app (Flask): The Flask application instance.
        auth_provider (AuthProvider): The active authentication provider.
    """

    def __init__(self, app=None):
        """Initialize the auth manager.

        Args:
            app (Flask, optional): Flask application instance. Defaults to None.
        """
        self.app = app
        self.auth_provider = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the auth manager with the Flask app.

        Args:
            app (Flask): Flask application instance.
        """
        self.app = app
        provider_type = "mock" if app.config.get("TESTING") else "keycloak"
        self.auth_provider = AuthProvider.create_provider(provider_type)

    def login_required(self, f):
        """Require authentication for routes.

        This decorator verifies the JWT token in the request header and adds
        the authenticated user information to Flask's g object.

        Args:
            f (callable): The route function to protect.

        Returns:
            callable: The decorated function.
        """

        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                raise Unauthorized("No authorization header")

            try:
                token_type, token = auth_header.split()
                if token_type.lower() != "bearer":
                    raise Unauthorized("Invalid token type")
            except ValueError:
                raise Unauthorized("Invalid authorization header format")

            try:
                claims = self.auth_provider.verify_token(token)
                g.user = claims
                return f(*args, **kwargs)
            except Exception as e:
                logger.error("Authentication failed", error=str(e))
                raise Unauthorized("Invalid token")

        return decorated_function

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current user.

        Returns:
            Optional[Dict[str, Any]]: User information if authenticated, None otherwise.
        """
        return getattr(g, "user", None)


# Global instance
auth_manager = AuthManager()
