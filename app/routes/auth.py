"""Authentication routes for the application."""

from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from ..auth import auth_manager

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login")
def login():
    """Redirect to authentication provider's login page."""
    provider = current_app.config.get("AUTH_PROVIDER", "keycloak")
    if provider == "keycloak":
        return redirect(auth_manager.get_login_url())
    elif provider == "okta":
        # Okta typically handles login via the frontend
        return jsonify(
            {
                "auth_url": current_app.config["OKTA_ISSUER"],
                "client_id": current_app.config["OKTA_CLIENT_ID"],
            }
        )
    else:
        return jsonify({"error": f"Unsupported auth provider: {provider}"}), 400


@bp.route("/callback")
def callback():
    """Handle OAuth callback from authentication provider."""
    provider = current_app.config.get("AUTH_PROVIDER", "keycloak")
    error = request.args.get("error")
    if error:
        return jsonify({"error": error}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "No code provided"}), 400

    try:
        if provider == "keycloak":
            # Exchange code for tokens using Keycloak
            token_response = auth_manager.get_token(code)
        elif provider == "okta":
            # Okta token exchange should be handled by the frontend
            return jsonify({"error": "Okta callback should be handled by frontend"}), 400
        else:
            return jsonify({"error": f"Unsupported auth provider: {provider}"}), 400

        # Store tokens in session
        session["access_token"] = token_response["access_token"]
        session["refresh_token"] = token_response.get("refresh_token")

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
    # Clear session
    session.clear()

    # Get provider type
    provider = current_app.config.get("AUTH_PROVIDER", "keycloak")

    if provider == "keycloak":
        # Redirect to Keycloak logout
        return redirect(auth_manager.get_logout_url())
    elif provider == "okta":
        # Return Okta logout URL for frontend to handle
        return jsonify({"logout_url": f"{current_app.config['OKTA_ISSUER']}/v1/logout"})
    else:
        return jsonify({"error": f"Unsupported auth provider: {provider}"}), 400
