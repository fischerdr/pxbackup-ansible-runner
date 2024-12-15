"""Request validation schemas using Pydantic."""

from pydantic import BaseModel, Field, validator, root_validator
from typing import Dict, Any, Optional
import re


class CreateClusterRequest(BaseModel):
    """Validation schema for cluster creation request."""

    name: str = Field(
        ..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
    )
    kubeconfig: Optional[str] = Field(
        None,
        description="Base64 encoded kubeconfig. Either this or kubeconfig_vault_path must be provided",
    )
    kubeconfig_vault_path: Optional[str] = Field(
        None,
        description="Path to kubeconfig in Vault. Either this or kubeconfig must be provided",
    )
    service_account: str = Field(
        ..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
    )
    namespace: str = Field(
        ..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
    )
    force: bool = Field(
        False, description="If true, recreate the cluster even if it already exists"
    )

    @validator("name")
    def validate_name(cls, v):
        if "--" in v:
            raise ValueError("Cluster name cannot contain consecutive hyphens")
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError(
                "Cluster name must start and end with alphanumeric character and contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @validator("service_account")
    def validate_service_account(cls, v):
        if "--" in v:
            raise ValueError("Service account name cannot contain consecutive hyphens")
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError(
                "Service account must start and end with alphanumeric character and contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @validator("namespace")
    def validate_namespace(cls, v):
        if "--" in v:
            raise ValueError("Namespace cannot contain consecutive hyphens")
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError(
                "Namespace must start and end with alphanumeric character and contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @validator("kubeconfig")
    def validate_kubeconfig(cls, v):
        if v is not None:
            try:
                import base64

                base64.b64decode(v)
            except Exception:
                raise ValueError("Kubeconfig must be a valid base64 encoded string")
        return v

    @root_validator
    def validate_kubeconfig_source(cls, values):
        kubeconfig = values.get("kubeconfig")
        vault_path = values.get("kubeconfig_vault_path")

        if kubeconfig is None and vault_path is None:
            raise ValueError(
                "Either kubeconfig or kubeconfig_vault_path must be provided"
            )
        if kubeconfig is not None and vault_path is not None:
            raise ValueError(
                "Only one of kubeconfig or kubeconfig_vault_path should be provided"
            )

        return values


class UpdateServiceAccountRequest(BaseModel):
    """Validation schema for service account update request."""

    cluster_name: str = Field(
        ..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
    )
    service_account: str = Field(
        ..., min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
    )


class ClusterStatusResponse(BaseModel):
    """Response schema for cluster status."""

    name: str
    status: str
    created_at: str
    updated_at: str
    service_account: Optional[str]
    playbook_status: Optional[str]
