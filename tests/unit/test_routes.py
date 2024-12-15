"""Unit tests for API routes."""

import json
import pytest
from app.models import Cluster, AuditLog, PlaybookExecution


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"


def test_create_cluster(client, auth_headers, sample_cluster, mock_vault, mock_ansible):
    """Test cluster creation."""
    response = client.post(
        "/api/v1/clusters", headers=auth_headers, json=sample_cluster
    )
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data["name"] == sample_cluster["name"]
    assert data["status"] == "created"


def test_create_duplicate_cluster(client, auth_headers, sample_cluster, db_cluster):
    """Test creating a cluster with duplicate name."""
    response = client.post(
        "/api/v1/clusters", headers=auth_headers, json=sample_cluster
    )
    assert response.status_code == 409


def test_update_service_account(
    client, auth_headers, db_cluster, mock_vault, mock_ansible
):
    """Test service account update."""
    update_data = {"service_account": "new-sa", "namespace": "new-ns"}
    response = client.post(
        f"/api/v1/clusters/{db_cluster.name}/service-account",
        headers=auth_headers,
        json=update_data,
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["service_account"] == update_data["service_account"]
    assert data["namespace"] == update_data["namespace"]


def test_check_cluster_status(client, auth_headers, db_cluster, mock_inventory):
    """Test cluster status check."""
    response = client.get(
        f"/api/v1/clusters/{db_cluster.name}/status", headers=auth_headers
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"


def test_check_nonexistent_cluster_status(client, auth_headers):
    """Test status check for non-existent cluster."""
    response = client.get("/api/v1/clusters/nonexistent/status", headers=auth_headers)
    assert response.status_code == 404


def test_missing_auth_header(client, sample_cluster):
    """Test request without auth header."""
    response = client.post("/api/v1/clusters", json=sample_cluster)
    assert response.status_code == 401


def test_invalid_auth_token(client, sample_cluster, mock_keycloak):
    """Test request with invalid auth token."""
    mock_keycloak.return_value.verify_access_token.side_effect = Exception(
        "Invalid token"
    )
    headers = {"Authorization": "Bearer invalid-token"}
    response = client.post("/api/v1/clusters", headers=headers, json=sample_cluster)
    assert response.status_code == 401


def test_invalid_request_data(client, auth_headers):
    """Test request with invalid data."""
    response = client.post(
        "/api/v1/clusters", headers=auth_headers, json={"invalid": "data"}
    )
    assert response.status_code == 400
