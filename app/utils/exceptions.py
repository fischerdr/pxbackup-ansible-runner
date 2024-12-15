"""Custom exception classes for the API."""

class APIError(Exception):
    """Base exception for API errors."""
    def __init__(self, message: str, status_code: int = 400, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)

class ValidationError(APIError):
    """Raised when request validation fails."""
    def __init__(self, message: str):
        super().__init__(message, 400, 'VALIDATION_ERROR')

class AuthenticationError(APIError):
    """Raised when authentication fails."""
    def __init__(self, message: str):
        super().__init__(message, 401, 'AUTHENTICATION_ERROR')

class AuthorizationError(APIError):
    """Raised when authorization fails."""
    def __init__(self, message: str):
        super().__init__(message, 403, 'AUTHORIZATION_ERROR')

class ResourceNotFoundError(APIError):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str):
        super().__init__(message, 404, 'RESOURCE_NOT_FOUND')

class ResourceConflictError(APIError):
    """Raised when there's a conflict with existing resources."""
    def __init__(self, message: str):
        super().__init__(message, 409, 'RESOURCE_CONFLICT')

class ExternalServiceError(APIError):
    """Raised when an external service (Vault, K8s, etc.) fails."""
    def __init__(self, message: str, service: str):
        super().__init__(
            message, 
            502, 
            f'EXTERNAL_SERVICE_ERROR_{service.upper()}'
        )
