"""Centralized logging configuration for the application.

This module provides a unified logging configuration using structlog for structured
logging across the application. It's designed to work well in Kubernetes environments
by providing JSON-formatted logs for better integration with log aggregation systems
like ELK, Splunk, or Cloud logging solutions.

Environment Variables:
    FLASK_ENV: The application environment ('development' or 'production').
               Affects the logging format and verbosity.
    LOG_LEVEL: The logging level (default: 'INFO'). Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    POD_NAME: Kubernetes pod name (automatically set in k8s environment)
    POD_NAMESPACE: Kubernetes namespace (automatically set in k8s environment)
    NODE_NAME: Kubernetes node name (automatically set in k8s environment)
"""

import os
import logging
import structlog
from typing import Dict


def get_k8s_context() -> Dict[str, str]:
    """Gather Kubernetes-specific context for logging.

    Retrieves environment variables typically available in a Kubernetes pod
    for enhanced logging context in containerized environments.

    Returns:
        Dict[str, str]: Dictionary containing Kubernetes-specific context
                       like pod name, namespace, and node name.
    """
    return {
        "pod_name": os.getenv("POD_NAME", "unknown"),
        "namespace": os.getenv("POD_NAMESPACE", "unknown"),
        "node_name": os.getenv("NODE_NAME", "unknown"),
    }


def configure_logging(
    app_name: str = "pxbackup-ansible-runner",
) -> structlog.BoundLogger:
    """Configure structured logging for the application.

    This function sets up structured logging using structlog with appropriate
    processors for formatting and output. It's optimized for Kubernetes environments
    with JSON output format and relevant k8s metadata included in logs.

    The configuration includes:
    - JSON formatting for better integration with log aggregation systems
    - Kubernetes context (pod, namespace, node) when running in k8s
    - ISO timestamp format for consistent time representation
    - Log level configuration via environment variable
    - Different formatting for development (human-readable) vs production (JSON)

    Args:
        app_name (str): The name of the application for log identification.
                       Defaults to "pxbackup-ansible-runner".

    Returns:
        structlog.BoundLogger: A configured logger instance for the application.

    Example:
        >>> logger = configure_logging("my-app")
        >>> logger.info("Application started", version="1.0.0")
    """
    # Set log level from environment variable
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_level_num = getattr(logging, log_level.upper(), logging.INFO)

    # Get Kubernetes context
    k8s_context = get_k8s_context()

    # Configure structlog
    base_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # Add Kubernetes context to all log entries
        lambda logger, method_name, event_dict: {
            **event_dict,
            **k8s_context,
            "app_name": app_name,
        },
    ]

    # Configure based on environment
    env = os.getenv("FLASK_ENV", "development")
    if env == "development":
        # More verbose logging in development with human-readable format
        processors = base_processors + [
            structlog.dev.ConsoleRenderer(),
        ]
    else:
        processors = base_processors + [
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Create a shared logger instance
    logger = structlog.get_logger(app_name)

    # Add environment-specific configuration
    env = os.getenv("FLASK_ENV", "development")
    if env == "development":
        # More verbose logging in development with human-readable format
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ]
        )

    return logger
