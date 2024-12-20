"""Flask application factory and configuration module.

This module initializes the Flask application and its extensions, including SQLAlchemy
for database management and PrometheusMetrics for monitoring. It follows the application
factory pattern to create and configure the Flask application instance.
"""

import os
from urllib.parse import urlparse

from flask import Flask
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from prometheus_flask_exporter import PrometheusMetrics

from .auth import auth_manager

db = SQLAlchemy()
metrics = PrometheusMetrics(app=None)
auth_manager = auth_manager

# Parse Redis URL for configuration
redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
redis_parts = urlparse(redis_url)

# Initialize limiter with Redis storage
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=redis_url,
)

# Initialize cache with Redis
cache = Cache(config={"CACHE_TYPE": "redis", "CACHE_REDIS_URL": redis_url, "CACHE_DEFAULT_TIMEOUT": 300})


def create_app(environment=None):
    """Create and configure the Flask application.

    This function serves as the application factory, creating a new Flask instance
    and configuring it with the necessary extensions and settings. It follows Flask's
    application factory pattern for better modularity and testing capabilities.

    Args:
        environment (str, optional): The environment to configure the app for.
            Defaults to None. Use 'testing' for test environment.

    Returns:
        Flask: A configured Flask application instance ready for use.
    """
    app = Flask(__name__)

    # Configure SQLAlchemy
    if environment == "testing":
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Configure Redis for caching and rate limiting
    app.config.update({"CACHE_TYPE": "redis", "CACHE_REDIS_URL": redis_url, "CACHE_DEFAULT_TIMEOUT": 300, "REDIS_URL": redis_url})

    # Initialize extensions
    db.init_app(app)
    metrics.init_app(app)
    auth_manager.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)

    # Load configuration from Kubernetes ConfigMap
    app.config["GITHUB_TOKEN"] = os.environ.get("GITHUB_TOKEN")
    app.config["PLAYBOOKS_DIR"] = os.environ.get("PLAYBOOKS_DIR", "/playbooks")
    app.config["VAULT_ADDR"] = os.environ.get("VAULT_ADDR")
    app.config["OKTA_ISSUER"] = os.environ.get("OKTA_ISSUER")
    app.config["OKTA_CLIENT_ID"] = os.environ.get("OKTA_CLIENT_ID")

    with app.app_context():
        # Import routes
        from . import routes

        app.register_blueprint(routes.bp, url_prefix="/api/v1")

        # Create database tables
        db.create_all()

    return app
