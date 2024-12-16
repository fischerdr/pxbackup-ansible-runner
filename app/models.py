"""Database models for the application.

This module defines the SQLAlchemy models that represent the database schema
for the application. It includes models for audit logging, cluster management,
and playbook execution tracking.
"""

from datetime import datetime, timezone

from . import db
from .schemas import PlaybookExecutionResponse


def get_utc_now():
    """Get the current UTC time with timezone information.

    Returns:
        datetime: Current UTC datetime with timezone information.
    """
    return datetime.now(timezone.utc)


class AuditLog(db.Model):
    """Model for tracking user actions and system events.

    This model stores audit information including timestamps, user actions,
    and related cluster operations for security and compliance purposes.

    Attributes:
        id (int): Primary key for the audit log entry.
        timestamp (datetime): When the action occurred (UTC).
        user_id (str): Identifier of the user who performed the action.
        action (str): Description of the action performed.
        details (str): Additional details about the action.
        status (str): Current status of the audited action.
        cluster_id (int): Foreign key to the related cluster.
    """

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(
        db.DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    user_id = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    status = db.Column(db.String(50))
    cluster_id = db.Column(db.Integer, db.ForeignKey("cluster.id"), nullable=True)


class Cluster(db.Model):
    """Model representing a Kubernetes cluster configuration.

    This model stores information about Kubernetes clusters including authentication
    details, namespace configuration, and current status. It maintains relationships
    with audit logs and playbook executions.

    Attributes:
        id (int): Primary key for the cluster.
        name (str): Unique name of the cluster.
        kubeconfig (str): Kubernetes configuration data.
        kubeconfig_vault_path (str): Path to the kubeconfig in Vault.
        service_account (str): Service account for cluster access.
        namespace (str): Kubernetes namespace to operate in.
        status (str): Current status of the cluster.
        created_at (datetime): When the cluster was added.
        updated_at (datetime): Last modification timestamp.
        playbook_executions (list): Related playbook executions.
        audit_logs (list): Related audit log entries.
    """

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    kubeconfig = db.Column(db.Text, nullable=True)
    kubeconfig_vault_path = db.Column(db.String(255), nullable=True)
    service_account = db.Column(db.String(255), nullable=False)
    namespace = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pending")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    # Relationships
    playbook_executions = db.relationship(
        "PlaybookExecution", backref="cluster", lazy=True, cascade="all, delete-orphan"
    )
    audit_logs = db.relationship(
        "AuditLog", backref="cluster", lazy=True, cascade="all, delete-orphan"
    )


class PlaybookExecution(db.Model):
    """Model for tracking Ansible playbook executions.

    This model records information about Ansible playbook runs, including their
    status, timing, and relationship to specific clusters.

    Attributes:
        id (int): Primary key for the execution record.
        playbook_name (str): Name of the executed playbook.
        status (str): Current status of the execution.
        started_at (datetime): When the execution began.
        completed_at (datetime): When the execution finished.
        result (str): Result of the execution.
        cluster_id (int): Foreign key to the related cluster.
    """

    id = db.Column(db.Integer, primary_key=True)
    playbook_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    completed_at = db.Column(db.DateTime(timezone=True))
    result = db.Column(db.Text)
    cluster_id = db.Column(db.Integer, db.ForeignKey("cluster.id"), nullable=False)

    def to_dict(self) -> dict:
        """Convert playbook execution to dictionary format.

        Returns:
            dict: Dictionary representation of the playbook execution.
        """
        return PlaybookExecutionResponse(
            id=self.id,
            playbook_name=self.playbook_name,
            status=self.status,
            started_at=self.started_at.isoformat() if self.started_at else None,
            completed_at=self.completed_at.isoformat() if self.completed_at else None,
            result=self.result,
            cluster_id=self.cluster_id,
        ).dict()
