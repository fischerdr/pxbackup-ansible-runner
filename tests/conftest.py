"""Test configuration and fixtures."""

import os
import pytest
from flask import Flask
from app import create_app, db
from app.models import Cluster, AuditLog, PlaybookExecution


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("OKTA_ISSUER", "https://test-issuer.okta.com")
    monkeypatch.setenv("OKTA_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("K8S_API_URL", "https://kubernetes.default.svc")
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("TESTING", "true")


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    # Set test config
    os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"
    os.environ["VAULT_ADDR"] = "http://localhost:8200"
    os.environ["VAULT_TOKEN"] = "test-token"
    os.environ["INVENTORY_API_URL"] = "http://localhost:8080"
    os.environ["KEYCLOAK_URL"] = "http://localhost:8080"
    os.environ["KEYCLOAK_REALM"] = "test-realm"
    os.environ["GITEA_URL"] = "http://localhost:3000"
    os.environ["GITEA_PLAYBOOKS_REPO"] = "test/playbooks"

    app = create_app()
    app.config["TESTING"] = True

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
    return {"Authorization": "Bearer test-token", "Content-Type": "application/json"}


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
    """Create a test cluster."""
    with app.app_context():
        cluster = Cluster(
            name="test-cluster",
            kubeconfig="test-kubeconfig",
            service_account="test-sa",
            namespace="test-ns",
            status="active",
        )
        db.session.add(cluster)
        db.session.commit()
        yield cluster
        db.session.delete(cluster)
        db.session.commit()


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
    mock.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value.status = (
        200
    )
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
    mock = mocker.patch("ansible.playbook.PlayBook")
    mock.return_value.run.return_value = {"status": "success"}
    return mock
