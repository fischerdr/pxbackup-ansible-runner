"""Vault client utility for interacting with HashiCorp Vault.

This module provides a singleton client for interacting with HashiCorp Vault,
configured using environment variables.

Required environment variables:
    VAULT_URL: The URL of the Vault server
    VAULT_ADDR: Alternative to VAULT_URL (for compatibility)
"""

import os
from typing import Optional

import hvac


class VaultClient:
    """Singleton class for Vault client."""

    _instance = None
    _client: Optional[hvac.Client] = None

    def __new__(cls):
        """Ensure only one instance of VaultClient exists."""
        if cls._instance is None:
            cls._instance = super(VaultClient, cls).__new__(cls)
        return cls._instance

    @property
    def client(self) -> hvac.Client:
        """Get or create the hvac client instance.

        Returns:
            hvac.Client: Configured Vault client

        Raises:
            ValueError: If neither VAULT_URL nor VAULT_ADDR environment variables are set
        """
        if self._client is None:
            # Try VAULT_URL first, fall back to VAULT_ADDR for compatibility
            vault_url = os.environ.get("VAULT_URL") or os.environ.get("VAULT_ADDR")
            if not vault_url:
                raise ValueError(
                    "Neither VAULT_URL nor VAULT_ADDR environment variables are set"
                )

            self._client = hvac.Client(
                url=vault_url,
                verify=True,  # Verify SSL by default
            )
        return self._client

    @property
    def url(self) -> str:
        """Get the Vault server URL.

        Returns:
            str: Vault server URL from environment variables
        """
        return os.environ.get("VAULT_URL") or os.environ.get("VAULT_ADDR", "")


# Create singleton instance
vault_client = VaultClient()
