"""Authentication module for the application."""

import os
from functools import wraps
from flask import request, jsonify, current_app, session, redirect, url_for
from werkzeug.exceptions import Unauthorized
import jwt
import requests
from urllib.parse import urlencode
import hvac


class AuthManager:
    """Manages authentication and authorization."""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the auth manager with the Flask app."""
        self.app = app

        # Keycloak configuration
        self.keycloak_url = app.config["KEYCLOAK_URL"]
        self.realm_name = app.config["KEYCLOAK_REALM"]
        self.client_id = app.config["KEYCLOAK_CLIENT_ID"]
        self.client_secret = app.config["KEYCLOAK_CLIENT_SECRET"]

        # Vault configuration
        self.vault_client = hvac.Client(
            url=app.config["VAULT_ADDR"], token=app.config.get("VAULT_TOKEN")
        )

        # Cache JWKS
        self.jwks = self._get_jwks()

    def _get_jwks(self):
        """Get the JSON Web Key Set from Keycloak."""
        url = f"{self.keycloak_url}/realms/{self.realm_name}/protocol/openid-connect/certs"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def login_required(self, f):
        """Decorator to require authentication for routes."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = self._get_token_from_header()
            if not token:
                return redirect(url_for("auth.login"))

            try:
                decoded_token = self.validate_token(token)
                # Add user info to flask.g
                current_app.g.user = decoded_token
                return f(*args, **kwargs)
            except Exception as e:
                current_app.logger.error(f"Token validation failed: {str(e)}")
                return redirect(url_for("auth.login"))

        return decorated_function

    def _get_token_from_header(self):
        """Extract token from Authorization header."""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        return None

    def validate_token(self, token):
        """Validate the JWT token."""
        try:
            header = jwt.get_unverified_header(token)
            key = self._find_signing_key(header["kid"])

            decoded_token = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=f"{self.keycloak_url}/realms/{self.realm_name}",
            )

            return decoded_token
        except Exception as e:
            current_app.logger.error(f"Token validation error: {str(e)}")
            raise Unauthorized("Invalid token")

    def _find_signing_key(self, kid):
        """Find the signing key in JWKS."""
        for key in self.jwks["keys"]:
            if key["kid"] == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        raise ValueError("Signing key not found")

    def get_login_url(self):
        """Get the Keycloak login URL."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": url_for("auth.callback", _external=True),
        }
        return f"{self.keycloak_url}/realms/{self.realm_name}/protocol/openid-connect/auth?{urlencode(params)}"

    def get_token(self, code):
        """Exchange authorization code for tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": url_for("auth.callback", _external=True),
        }

        response = requests.post(
            f"{self.keycloak_url}/realms/{self.realm_name}/protocol/openid-connect/token",
            data=data,
        )
        response.raise_for_status()
        return response.json()

    def get_vault_token(self, username, password):
        """Get a Vault token using userpass auth."""
        try:
            result = self.vault_client.auth.userpass.login(
                username=username, password=password
            )
            return result["auth"]["client_token"]
        except Exception as e:
            current_app.logger.error(f"Vault authentication error: {str(e)}")
            raise Unauthorized("Invalid Vault credentials")


auth_manager = AuthManager()
