"""Monitoring utilities."""

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from typing import Callable

from flask import request
from prometheus_client import Counter, Histogram

# Metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

REQUEST_DURATION = Histogram(
    "request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status"],
)

REQUEST_COUNT = Counter(
    "request_count_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

PLAYBOOK_EXECUTION_DURATION = Histogram(
    "playbook_execution_duration_seconds",
    "Playbook execution duration in seconds",
    ["playbook_name", "status"],
)

PLAYBOOK_EXECUTION_COUNT = Counter(
    "playbook_execution_count_total",
    "Total number of playbook executions",
    ["playbook_name", "status"],
)

VAULT_OPERATION_DURATION = Histogram(
    "vault_operation_duration_seconds",
    "Vault operation duration in seconds",
    ["operation", "status"],
)

VAULT_OPERATION_COUNT = Counter(
    "vault_operation_count_total",
    "Total number of Vault operations",
    ["operation", "status"],
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
                status = getattr(e, "status_code", 500)
                raise
            finally:
                duration = time.time() - start_time
                http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
                http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
                    duration
                )
                REQUEST_DURATION.labels(method=method, endpoint=endpoint, status=status).observe(
                    duration
                )
                REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()

        return decorated_function

    return decorator


@contextmanager
def track_playbook_execution(playbook_name):
    """Track playbook execution metrics."""
    start_time = time.time()
    try:
        yield
        duration = time.time() - start_time
        PLAYBOOK_EXECUTION_DURATION.labels(playbook_name=playbook_name, status="success").observe(
            duration
        )
        PLAYBOOK_EXECUTION_COUNT.labels(playbook_name=playbook_name, status="success").inc()
    except Exception as e:
        duration = time.time() - start_time
        PLAYBOOK_EXECUTION_DURATION.labels(playbook_name=playbook_name, status="failure").observe(
            duration
        )
        PLAYBOOK_EXECUTION_COUNT.labels(playbook_name=playbook_name, status="failure").inc()
        raise e


def record_vault_operation(operation, start_time, success):
    """Record Vault operation metrics."""
    duration = time.time() - start_time
    status = "success" if success else "failure"
    VAULT_OPERATION_DURATION.labels(operation=operation, status=status).observe(duration)
    VAULT_OPERATION_COUNT.labels(operation=operation, status=status).inc()
