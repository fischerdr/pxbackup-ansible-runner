"""Error handlers for the API endpoints.

This module contains all the error handlers used by the API endpoints to ensure
consistent error responses across the application.
"""

from typing import Any, Dict, Tuple

from flask import current_app, jsonify


def handle_validation_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Handle validation errors.

    Args:
        error: The validation error that occurred

    Returns:
        Tuple containing the error response and HTTP status code
    """
    current_app.logger.warning(f"Validation error: {str(error)}")
    return jsonify({"error": str(error)}), 400


def handle_resource_not_found_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Handle resource not found errors.

    Args:
        error: The resource not found error that occurred

    Returns:
        Tuple containing the error response and HTTP status code
    """
    current_app.logger.warning(f"Resource not found: {str(error)}")
    return jsonify({"error": str(error)}), 404


def handle_resource_exists_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Handle resource already exists errors.

    Args:
        error: The resource already exists error that occurred

    Returns:
        Tuple containing the error response and HTTP status code
    """
    current_app.logger.warning(f"Resource already exists: {str(error)}")
    return jsonify({"error": str(error)}), 409


def handle_external_service_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Handle external service errors.

    Args:
        error: The external service error that occurred

    Returns:
        Tuple containing the error response and HTTP status code
    """
    current_app.logger.error(f"External service error: {str(error)}")
    return jsonify({"error": str(error)}), 502


def handle_authentication_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Handle authentication errors.

    Args:
        error: The authentication error that occurred

    Returns:
        Tuple containing the error response and HTTP status code
    """
    current_app.logger.warning(f"Authentication error: {str(error)}")
    return jsonify({"error": str(error)}), 401


def handle_internal_error(error: Exception) -> Tuple[Dict[str, Any], int]:
    """Handle internal server errors.

    Args:
        error: The internal error that occurred

    Returns:
        Tuple containing the error response and HTTP status code
    """
    current_app.logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500
