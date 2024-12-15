"""Unit tests for API routes."""

import json

import pytest

from app.models import AuditLog, Cluster, PlaybookExecution


def test_health_check(client, mock_vault, mocker):
    """Test health check endpoint."""
    # Mock Redis connection
    mock_redis = mocker.Mock()
    mock_redis.ping.return_value = True
    mocker.patch("redis.Redis", return_value=mock_redis)

    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_create_cluster(client, auth_headers, sample_cluster, mock_vault, mock_ansible):
    """Test cluster creation."""
    with client.application.app_context():
        response = client.post("/api/v1/clusters", headers=auth_headers, json=sample_cluster)
        assert response.status_code == 201
        assert response.json["name"] == sample_cluster["name"]


def test_create_duplicate_cluster(client, auth_headers, sample_cluster, db_cluster):
    """Test creating a cluster with duplicate name."""
    with client.application.app_context():
        cluster = db_cluster()  # Get fresh cluster instance
        response = client.post("/api/v1/clusters", headers=auth_headers, json=sample_cluster)
        assert response.status_code == 409


def test_update_service_account(client, auth_headers, db_cluster, mock_vault, mock_ansible):
    """Test service account update."""
    with client.application.app_context():
        cluster = db_cluster()  # Get fresh cluster instance
        update_data = {"service_account": "new-sa", "namespace": "new-ns"}
        response = client.post(
            f"/api/v1/clusters/{cluster.name}/service-account",
            headers=auth_headers,
            json=update_data,
        )
        assert response.status_code == 200


def test_check_cluster_status(client, auth_headers, db_cluster, mock_inventory):
    """Test cluster status check."""
    with client.application.app_context():
        cluster = db_cluster()  # Get fresh cluster instance
        response = client.get(f"/api/v1/clusters/{cluster.name}/status", headers=auth_headers)
        assert response.status_code == 200


def test_check_nonexistent_cluster_status(client, auth_headers):
    """Test checking status of non-existent cluster."""
    response = client.get("/api/v1/clusters/nonexistent/status", headers=auth_headers)
    assert response.status_code == 404


def test_missing_auth_header(client):
    """Test request without auth header."""
    response = client.get("/api/v1/clusters/test/status")
    assert response.status_code == 401


def test_invalid_auth_token(client):
    """Test request with invalid auth token."""
    headers = {"Authorization": "Bearer invalid-token"}
    response = client.get("/api/v1/clusters/test/status", headers=headers)
    assert response.status_code == 401


def test_invalid_request_data(client, auth_headers):
    """Test request with invalid data."""
    response = client.post("/api/v1/clusters", headers=auth_headers, json={"invalid": "data"})
    assert response.status_code == 400
