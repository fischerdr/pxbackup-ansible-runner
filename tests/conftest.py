"""Test configuration and fixtures."""

import os

import pytest
from flask import Flask

from app import create_app, db
from app.models import AuditLog, Cluster, PlaybookExecution


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("OKTA_ISSUER", "https://test-issuer.okta.com")
    monkeypatch.setenv("OKTA_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("K8S_API_URL", "https://kubernetes.default.svc")
    monkeypatch.setenv("VAULT_ADDR", "http://localhost:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("INVENTORY_API_URL", "http://localhost:8080")
    monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8080")
    monkeypatch.setenv("KEYCLOAK_REALM", "test-realm")
    monkeypatch.setenv("GITEA_URL", "http://localhost:3000")
    monkeypatch.setenv("GITEA_PLAYBOOKS_REPO", "test/playbooks")
    monkeypatch.setenv("AUTH_PROVIDER", "keycloak")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "test-secret")


@pytest.fixture(autouse=True)
def cleanup_db(app):
    """Clean up database session after each test."""
    yield
    with app.app_context():
        db.session.rollback()
        db.session.remove()
        db.session.close_all()


@pytest.fixture(autouse=True)
async def mock_auth_provider(mocker):
    """Mock authentication provider."""
    mock_provider = mocker.AsyncMock()

    async def async_verify_token(token):
        if token == "test-token":
            return {"sub": "test-user", "preferred_username": "test-user"}
        raise Unauthorized("Invalid token")

    mock_provider.verify_token = async_verify_token
    mock_provider.get_user_info.return_value = {
        "id": "test-user",
        "name": "test-user",
        "email": "test@example.com",
    }

    # Mock the auth manager
    mock_manager = mocker.AsyncMock()
    mock_manager.auth_provider = mock_provider
    mock_manager.verify_token = async_verify_token
    mock_manager.get_user_info = mock_provider.get_user_info

    mocker.patch("app.auth.auth_manager", mock_manager)
    return mock_provider


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["CACHE_TYPE"] = "SimpleCache"
    app.config["CACHE_DEFAULT_TIMEOUT"] = 300

    # Initialize extensions
    from flask_caching import Cache

    cache = Cache()
    cache.init_app(app)
    app.extensions["cache"] = {cache: cache}

    # Create tables in memory
    with app.app_context():
        db.create_all()

    yield app

    # Clean up
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def auth_headers():
    """Create mock authentication headers."""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
        "X-User-ID": "test-user",
        "X-User-Name": "test-user",
    }


@pytest.fixture
def sample_cluster():
    """Create a sample cluster object."""
    return {
        "name": "test-cluster",
        "kubeconfig": "test-kubeconfig",
        "service_account": "test-sa",
        "namespace": "test-ns",
    }


@pytest.fixture
def db_cluster(app):
    """Create a test cluster in the database."""

    def get_cluster():
        cluster = Cluster(
            name="test-cluster",
            namespace="test-ns",
            service_account="test-sa",
            kubeconfig="test-kubeconfig",
            created_by="test-user",
        )
        db.session.add(cluster)
        db.session.commit()
        return cluster

    return get_cluster


@pytest.fixture
def mock_vault(mocker):
    """Mock Vault client."""
    mock = mocker.patch("hvac.Client")
    mock.return_value.is_authenticated.return_value = True
    return mock


@pytest.fixture
def mock_inventory(mocker):
    """Mock inventory service."""
    mock = mocker.patch("aiohttp.ClientSession")
    mock.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value.status = 200
    mock.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value.json.return_value = {
        "status": "healthy"
    }
    return mock


@pytest.fixture
def mock_keycloak(mocker):
    """Mock Keycloak verifier."""
    mock = mocker.patch("okta_jwt_verifier.JWTVerifier")
    mock.return_value.verify_access_token.return_value = {
        "sub": "test-user",
        "scope": ["read", "write"],
    }
    return mock


@pytest.fixture
def mock_gitea(mocker):
    """Mock Gitea client."""
    mock = mocker.patch("git.Repo")
    return mock


@pytest.fixture
def mock_ansible(mocker):
    """Mock Ansible runner."""
    mock = mocker.patch("ansible_runner.Runner")
    mock.return_value.run.return_value = {"rc": 0, "stdout": "success"}
    return mock
