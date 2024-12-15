"""Monitoring and metrics utilities."""

from functools import wraps
from flask import request
from prometheus_client import Counter, Histogram
import time
from typing import Callable
from datetime import datetime, timezone

# Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

playbook_execution_duration_seconds = Histogram(
    'playbook_execution_duration_seconds',
    'Ansible playbook execution duration',
    ['playbook_name', 'status']
)

vault_operation_duration_seconds = Histogram(
    'vault_operation_duration_seconds',
    'Vault operation duration',
    ['operation', 'status']
)

def track_request_metrics() -> Callable:
    """Decorator to track request metrics."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            start_time = time.time()
            method = request.method
            endpoint = request.endpoint

            try:
                response = await f(*args, **kwargs)
                status = response[1] if isinstance(response, tuple) else 200
                return response
            except Exception as e:
                status = getattr(e, 'status_code', 500)
                raise
            finally:
                duration = time.time() - start_time
                http_requests_total.labels(
                    method=method,
                    endpoint=endpoint,
                    status=status
                ).inc()
                http_request_duration_seconds.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(duration)

        return decorated_function
    return decorator

def track_playbook_execution(playbook_name: str) -> None:
    """Track playbook execution metrics."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            start_time = time.time()
            try:
                result = await f(*args, **kwargs)
                status = 'success'
                return result
            except Exception:
                status = 'failure'
                raise
            finally:
                duration = time.time() - start_time
                playbook_execution_duration_seconds.labels(
                    playbook_name=playbook_name,
                    status=status
                ).observe(duration)
        return decorated_function
    return decorator

async def record_vault_operation(operation: str, start_time: float, success: bool) -> None:
    """Record Vault operation metrics."""
    duration = time.time() - start_time
    vault_operation_duration_seconds.labels(
        operation=operation,
        status='success' if success else 'failure'
    ).observe(duration)
