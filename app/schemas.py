"""Request and response schemas for the API endpoints."""

import base64
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateClusterRequest(BaseModel):
    """Schema for creating a new cluster."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="Name of the cluster. Must follow DNS naming conventions.",
    )
    service_account: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Service account name",
    )
    namespace: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Kubernetes namespace",
    )
    kubeconfig: Optional[str] = Field(
        None,
        description="Base64 encoded kubeconfig. Either this or kubeconfig_vault_path must be provided",
    )
    kubeconfig_vault_path: Optional[str] = Field(
        None,
        description="Path to kubeconfig in Vault. Either this or kubeconfig must be provided",
    )
    force: bool = Field(
        False,
        description="Force cluster creation even if it exists",
    )

    @field_validator("name")
    @classmethod
    def validate_cluster_name(cls, v: str) -> str:
        """Validate cluster name follows DNS and security conventions."""
        # DNS naming convention check
        if not v.replace("-", "").replace(".", "").isalnum():
            raise ValueError(
                "Cluster name must contain only alphanumeric characters, dots, and hyphens"
            )
        if not v[0].isalpha() or not v[-1].isalnum():
            raise ValueError(
                "Cluster name must start with a letter and end with an alphanumeric character"
            )
        # Security check
        if "--" in v:
            raise ValueError(
                "Name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, v: str) -> str:
        """Validate namespace follows Kubernetes and security conventions."""
        # Kubernetes naming convention check
        if not v.replace("-", "").isalnum():
            raise ValueError("Namespace must contain only alphanumeric characters and hyphens")
        if not v[0].isalpha() or not v[-1].isalnum():
            raise ValueError(
                "Namespace must start with a letter and end with an alphanumeric character"
            )
        # Security check
        if "--" in v:
            raise ValueError(
                "Namespace cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("service_account")
    @classmethod
    def validate_service_account(cls, v: str) -> str:
        """Validate service account name follows security conventions."""
        if "--" in v:
            raise ValueError(
                "Service account name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("kubeconfig")
    @classmethod
    def validate_kubeconfig(cls, v: Optional[str]) -> Optional[str]:
        """Validate base64 encoded kubeconfig if provided."""
        if v is not None:
            try:
                base64.b64decode(v)
            except Exception:
                raise ValueError("Kubeconfig must be base64 encoded")
        return v

    @model_validator(mode="after")
    def validate_kubeconfig_source(self) -> "CreateClusterRequest":
        """Ensure either kubeconfig or kubeconfig_vault_path is provided."""
        if bool(self.kubeconfig) == bool(self.kubeconfig_vault_path):
            raise ValueError("Exactly one of kubeconfig or kubeconfig_vault_path must be provided")
        return self


class UpdateServiceAccountRequest(BaseModel):
    """Schema for updating a service account."""

    cluster_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="Name of the cluster",
    )
    service_account: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="New service account name",
    )
    namespace: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Kubernetes namespace",
    )

    @field_validator("cluster_name")
    @classmethod
    def validate_cluster_name(cls, v: str) -> str:
        """Validate cluster name follows DNS and security conventions."""
        if not v.replace("-", "").replace(".", "").isalnum():
            raise ValueError(
                "Cluster name must contain only alphanumeric characters, dots, and hyphens"
            )
        if not v[0].isalpha() or not v[-1].isalnum():
            raise ValueError(
                "Cluster name must start with a letter and end with an alphanumeric character"
            )
        if "--" in v:
            raise ValueError(
                "Name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("service_account")
    @classmethod
    def validate_service_account(cls, v: str) -> str:
        """Validate service account name follows security conventions."""
        if "--" in v:
            raise ValueError(
                "Service account name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v


class PlaybookExecutionResponse(BaseModel):
    """Schema for playbook execution details."""

    id: int = Field(..., description="Execution ID")
    status: str = Field(..., description="Execution status")
    playbook: str = Field(..., description="Playbook name")
    start_time: str = Field(..., description="Start time in ISO format")
    command: str = Field(..., description="Executed command")
    pid: Optional[int] = Field(None, description="Process ID if running")
    return_code: Optional[int] = Field(None, description="Return code if completed")
    extra_vars: Dict = Field(..., description="Playbook variables")


class ClusterStatusResponse(BaseModel):
    """Schema for cluster status response."""

    id: int = Field(..., description="Cluster ID")
    name: str = Field(..., description="Cluster name")
    status: str = Field(..., description="Current cluster status")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    playbook_execution: Optional[PlaybookExecutionResponse] = Field(
        None, description="Latest playbook execution details"
    )
