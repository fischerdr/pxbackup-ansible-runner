"""Request validation schemas using Pydantic."""

import base64
import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateClusterRequest(BaseModel):
    """Validation schema for cluster creation request."""

    name: str = Field(..., min_length=1, max_length=255)
    kubeconfig: Optional[str] = Field(
        None,
        description="Base64 encoded kubeconfig. Either this or kubeconfig_vault_path must be provided",
    )
    kubeconfig_vault_path: Optional[str] = Field(
        None,
        description="Path to kubeconfig in Vault. Either this or kubeconfig must be provided",
    )
    service_account: str = Field(..., min_length=1, max_length=255)
    namespace: str = Field(..., min_length=1, max_length=255)
    force: bool = Field(
        False, description="If true, recreate the cluster even if it already exists"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if "--" in v:
            raise ValueError(
                "Name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("service_account")
    @classmethod
    def validate_service_account(cls, v: str) -> str:
        if "--" in v:
            raise ValueError(
                "Service account name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, v: str) -> str:
        if "--" in v:
            raise ValueError(
                "Namespace cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("kubeconfig")
    @classmethod
    def validate_kubeconfig(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                base64.b64decode(v)
            except Exception:
                raise ValueError("Kubeconfig must be a valid base64 encoded string")
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_kubeconfig_source(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        kubeconfig = values.get("kubeconfig")
        vault_path = values.get("kubeconfig_vault_path")

        if kubeconfig is None and vault_path is None:
            raise ValueError("Either kubeconfig or kubeconfig_vault_path must be provided")
        if kubeconfig is not None and vault_path is not None:
            raise ValueError("Only one of kubeconfig or kubeconfig_vault_path should be provided")

        return values


class UpdateServiceAccountRequest(BaseModel):
    """Validation schema for service account update request."""

    cluster_name: str = Field(..., min_length=1, max_length=255)
    service_account: str = Field(..., min_length=1, max_length=255)
    namespace: str = Field(..., min_length=1, max_length=255)

    @field_validator("service_account")
    @classmethod
    def validate_service_account(cls, v: str) -> str:
        if "--" in v:
            raise ValueError(
                "Service account name cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, v: str) -> str:
        if "--" in v:
            raise ValueError(
                "Namespace cannot contain double hyphens (--) as this can cause issues with shell commands"
            )
        return v


class ClusterStatusResponse(BaseModel):
    """Response schema for cluster status."""

    name: str
    status: str
    created_at: str
    updated_at: str
    service_account: Optional[str]
    playbook_status: Optional[str]
