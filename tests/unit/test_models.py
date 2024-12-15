"""Unit tests for database models."""

from datetime import datetime, timezone

import pytest

from app import db
from app.models import AuditLog, Cluster, PlaybookExecution


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
        cluster = db_cluster()
        log = AuditLog(
            user_id="test-user",
            action="create_cluster",
            details=f"Created cluster {cluster.name}",
            status="success",
        )
        db.session.add(log)
        db.session.commit()
        assert log.id is not None


def test_playbook_execution_creation(app, db_cluster):
    """Test playbook execution model creation."""
    with app.app_context():
        cluster = db_cluster()
        execution = PlaybookExecution(
            cluster_id=cluster.id,
            playbook_name="test-playbook",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(execution)
        db.session.commit()
        assert execution.id is not None


def test_cluster_relationships(app, db_cluster):
    """Test cluster model relationships."""
    with app.app_context():
        cluster = db_cluster()
        # Create related records
        log = AuditLog(
            user_id="test-user",
            action="create_cluster",
            details=f"Created cluster {cluster.name}",
            status="success",
            cluster_id=cluster.id,
        )
        db.session.add(log)
        execution = PlaybookExecution(
            cluster_id=cluster.id,
            playbook_name="test-playbook",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(execution)
        db.session.commit()

        # Test relationships
        assert len(cluster.audit_logs) > 0
        assert len(cluster.playbook_executions) > 0


def test_cascade_delete(app, db_cluster):
    """Test cascade delete behavior."""
    with app.app_context():
        cluster = db_cluster()
        # Create related records
        execution = PlaybookExecution(
            cluster_id=cluster.id,
            playbook_name="test-playbook",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.session.add(execution)
        db.session.commit()

        # Delete cluster
        db.session.delete(cluster)
        db.session.commit()

        # Verify cascade delete
        assert db.session.get(PlaybookExecution, execution.id) is None


def test_model_timestamps(app, db_cluster):
    """Test model timestamp fields."""
    with app.app_context():
        cluster = db_cluster()
        # Test cluster timestamps
        assert cluster.created_at is not None
        assert cluster.updated_at is not None

        # Update cluster
        import time
        from datetime import datetime, timezone

        original_updated_at = cluster.updated_at
        time.sleep(1)  # Add longer delay to ensure different timestamp
        cluster.service_account = "new-sa"
        db.session.commit()
        db.session.refresh(cluster)

        # Verify updated_at changed
        assert cluster.updated_at > original_updated_at
