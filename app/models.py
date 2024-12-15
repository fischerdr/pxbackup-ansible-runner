from . import db
from datetime import datetime, timezone


def get_utc_now():
    """Helper function to get current UTC time with timezone information"""
    return datetime.now(timezone.utc)


class AuditLog(db.Model):
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
    playbook_executions = db.relationship('PlaybookExecution', backref='cluster', lazy=True,
                                        cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='cluster', lazy=True,
                               cascade='all, delete-orphan')


class PlaybookExecution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    playbook_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    completed_at = db.Column(db.DateTime(timezone=True))
    result = db.Column(db.Text)
    cluster_id = db.Column(db.Integer, db.ForeignKey("cluster.id"), nullable=False)
