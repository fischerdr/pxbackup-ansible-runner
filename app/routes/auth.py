"""Authentication routes for the application."""

from flask import Blueprint, redirect, url_for, session, request, current_app, jsonify
from ..auth import auth_manager

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login")
def login():
    """Redirect to Keycloak login."""
    return redirect(auth_manager.get_login_url())


@bp.route("/callback")
def callback():
    """Handle OAuth callback from Keycloak."""
    error = request.args.get("error")
    if error:
        return jsonify({"error": error}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "No code provided"}), 400

    try:
        # Exchange code for tokens
        token_response = auth_manager.get_token(code)

        # Store tokens in session
        session["access_token"] = token_response["access_token"]
        session["refresh_token"] = token_response["refresh_token"]

        return redirect(url_for("main.index"))
    except Exception as e:
        current_app.logger.error(f"Token exchange error: {str(e)}")
        return jsonify({"error": "Authentication failed"}), 401


@bp.route("/vault-token", methods=["POST"])
def get_vault_token():
    """Get a Vault token using userpass authentication."""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    try:
        token = auth_manager.get_vault_token(username, password)
        return jsonify({"token": token})
    except Exception as e:
        return jsonify({"error": str(e)}), 401


@bp.route("/logout")
def logout():
    """Log out the user."""
    session.clear()
    return redirect(url_for("main.index"))
