"""Unit tests for database models."""

import pytest
from datetime import datetime, timezone
from app.models import Cluster, AuditLog, PlaybookExecution
from app import db


def test_cluster_creation(app, sample_cluster):
    """Test cluster model creation."""
    with app.app_context():
        cluster = Cluster(
            name=sample_cluster["name"],
            kubeconfig=sample_cluster["kubeconfig"],
            service_account=sample_cluster["service_account"],
            namespace=sample_cluster["namespace"],
        )
        db.session.add(cluster)
        db.session.commit()

        # Query the cluster
        saved_cluster = Cluster.query.filter_by(name=sample_cluster["name"]).first()
        assert saved_cluster is not None
        assert saved_cluster.name == sample_cluster["name"]
        assert saved_cluster.service_account == sample_cluster["service_account"]


def test_audit_log_creation(app, db_cluster):
    """Test audit log model creation."""
    with app.app_context():
        log = AuditLog(
            user_id="test-user",
            action="create_cluster",
            details=f"Created cluster {db_cluster.name}",
            status="success",
        )
        db.session.add(log)
        db.session.commit()

        # Query the log
        saved_log = AuditLog.query.filter_by(user_id="test-user").first()
        assert saved_log is not None
        assert saved_log.action == "create_cluster"
        assert saved_log.status == "success"


def test_playbook_execution_creation(app, db_cluster):
    """Test playbook execution model creation."""
    with app.app_context():
        execution = PlaybookExecution(
            cluster_id=db_cluster.id,
            playbook_name="test-playbook",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(execution)
        db.session.commit()

        # Query the execution
        saved_execution = PlaybookExecution.query.filter_by(
            cluster_id=db_cluster.id
        ).first()
        assert saved_execution is not None
        assert saved_execution.playbook_name == "test-playbook"
        assert saved_execution.status == "running"


def test_cluster_relationships(app, db_cluster):
    """Test cluster model relationships."""
    with app.app_context():
        # Create related records
        log = AuditLog(
            user_id="test-user",
            action="create_cluster",
            details=f"Created cluster {db_cluster.name}",
            status="success",
        )
        execution = PlaybookExecution(
            cluster_id=db_cluster.id,
            playbook_name="test-playbook",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.session.add_all([log, execution])
        db.session.commit()

        # Test relationships
        cluster = Cluster.query.filter_by(name=db_cluster.name).first()
        assert len(cluster.playbook_executions) == 1
        assert cluster.playbook_executions[0].playbook_name == "test-playbook"


def test_cascade_delete(app, db_cluster):
    """Test cascade delete behavior."""
    with app.app_context():
        # Create related records
        execution = PlaybookExecution(
            cluster_id=db_cluster.id,
            playbook_name="test-playbook",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(execution)
        db.session.commit()

        # Delete cluster
        db.session.delete(db_cluster)
        db.session.commit()

        # Verify cascade delete
        assert Cluster.query.filter_by(name=db_cluster.name).first() is None
        assert (
            PlaybookExecution.query.filter_by(cluster_id=db_cluster.id).first() is None
        )


def test_model_timestamps(app, db_cluster):
    """Test model timestamp fields."""
    with app.app_context():
        # Test cluster timestamps
        assert db_cluster.created_at is not None
        assert db_cluster.updated_at is not None

        # Update cluster
        original_updated_at = db_cluster.updated_at
        db_cluster.service_account = "new-sa"
        db.session.commit()

        # Verify updated_at changed
        assert db_cluster.updated_at > original_updated_at
