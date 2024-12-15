"""Application configuration management."""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


@dataclass
class Config:
    """Application configuration."""

    OKTA_ISSUER: str
    OKTA_CLIENT_ID: str
    VAULT_ADDR: str
    VAULT_TOKEN: str
    K8S_API_URL: str
    DEBUG: bool = False
    TESTING: bool = False
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    CACHE_TYPE: str = "redis"
    CACHE_REDIS_URL: Optional[str] = None
    RATE_LIMIT_DEFAULT: str = "200 per day"
    RATE_LIMIT_STORAGE_URL: Optional[str] = None
    INVENTORY_API_URL: Optional[str] = None

    @classmethod
    @lru_cache()
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls(
            OKTA_ISSUER=os.environ.get("OKTA_ISSUER", "https://test-issuer.okta.com"),
            OKTA_CLIENT_ID=os.environ.get("OKTA_CLIENT_ID", "test-client-id"),
            VAULT_ADDR=os.environ.get("VAULT_ADDR", "http://localhost:8200"),
            VAULT_TOKEN=os.environ.get("VAULT_TOKEN", "test-token"),
            K8S_API_URL=os.environ.get("K8S_API_URL", "https://kubernetes.default.svc"),
            DEBUG=os.environ.get("DEBUG", "").lower() == "true",
            TESTING=os.environ.get("TESTING", "").lower() == "true",
            SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
            CACHE_REDIS_URL=os.environ.get("REDIS_URL"),
            RATE_LIMIT_STORAGE_URL=os.environ.get("REDIS_URL"),
            INVENTORY_API_URL=os.environ.get("INVENTORY_API_URL"),
        )

    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
