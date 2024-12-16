"""Flask application factory and configuration module.

This module initializes the Flask application and its extensions, including SQLAlchemy
for database management and PrometheusMetrics for monitoring. It follows the application
factory pattern to create and configure the Flask application instance.
"""

import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from prometheus_flask_exporter import PrometheusMetrics

db = SQLAlchemy()
metrics = PrometheusMetrics(app=None)


def create_app():
    """Create and configure the Flask application.

    This function serves as the application factory, creating a new Flask instance
    and configuring it with the necessary extensions and settings. It follows Flask's
    application factory pattern for better modularity and testing capabilities.

    Returns:
        Flask: A configured Flask application instance ready for use.
    """
    app = Flask(__name__)

    # Configure SQLAlchemy
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize extensions
    db.init_app(app)
    metrics.init_app(app)

    # Load configuration from Kubernetes ConfigMap
    app.config["GITHUB_TOKEN"] = os.environ.get("GITHUB_TOKEN")
    app.config["PLAYBOOKS_DIR"] = os.environ.get("PLAYBOOKS_DIR", "/playbooks")
    app.config["VAULT_ADDR"] = os.environ.get("VAULT_ADDR")
    app.config["OKTA_ISSUER"] = os.environ.get("OKTA_ISSUER")
    app.config["OKTA_CLIENT_ID"] = os.environ.get("OKTA_CLIENT_ID")

    with app.app_context():
        # Import routes
        from . import routes

        app.register_blueprint(routes.bp)

        # Create database tables
        db.create_all()

    return app
