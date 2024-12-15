"""Unit tests for monitoring utilities."""

import time
import pytest
from app.utils.monitoring import (
    track_request_metrics,
    track_playbook_execution,
    record_vault_operation
)
from prometheus_client import REGISTRY

def test_request_metrics(app, client):
    """Test request metrics tracking."""
    with app.app_context():
        # Make a test request
        response = client.get('/api/v1/health')
        assert response.status_code == 200
        
        # Check metrics
        metrics = REGISTRY.get_sample_value(
            'http_requests_total',
            {'method': 'GET', 'endpoint': 'api.health_check', 'status': '200'}
        )
        assert metrics > 0

def test_playbook_execution_metrics(app):
    """Test playbook execution metrics."""
    with app.app_context():
        start_time = time.time()
        
        # Track a successful playbook execution
        with track_playbook_execution('test-playbook'):
            time.sleep(0.1)  # Simulate work
        
        # Check metrics
        metrics = REGISTRY.get_sample_value(
            'playbook_execution_duration_seconds_count',
            {'playbook_name': 'test-playbook', 'status': 'success'}
        )
        assert metrics > 0

def test_vault_operation_metrics(app):
    """Test Vault operation metrics."""
    with app.app_context():
        start_time = time.time()
        
        # Record a successful Vault operation
        record_vault_operation('read', start_time, True)
        
        # Check metrics
        metrics = REGISTRY.get_sample_value(
            'vault_operation_duration_seconds_count',
            {'operation': 'read', 'status': 'success'}
        )
        assert metrics > 0

def test_failed_playbook_execution_metrics(app):
    """Test failed playbook execution metrics."""
    with app.app_context():
        with pytest.raises(Exception):
            with track_playbook_execution('test-playbook'):
                raise Exception('Test failure')
        
        # Check metrics
        metrics = REGISTRY.get_sample_value(
            'playbook_execution_duration_seconds_count',
            {'playbook_name': 'test-playbook', 'status': 'failure'}
        )
        assert metrics > 0

def test_failed_vault_operation_metrics(app):
    """Test failed Vault operation metrics."""
    with app.app_context():
        start_time = time.time()
        
        # Record a failed Vault operation
        record_vault_operation('write', start_time, False)
        
        # Check metrics
        metrics = REGISTRY.get_sample_value(
            'vault_operation_duration_seconds_count',
            {'operation': 'write', 'status': 'failure'}
        )
        assert metrics > 0
