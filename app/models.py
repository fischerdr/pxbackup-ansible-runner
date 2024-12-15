from . import db
from datetime import datetime, timezone

def get_utc_now():
    """Helper function to get current UTC time with timezone information"""
    return datetime.now(timezone.utc)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    user_id = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    status = db.Column(db.String(50))

class Cluster(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cluster_name = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)
    service_account = db.Column(db.String(255), nullable=False)
    namespace = db.Column(db.String(255), nullable=False)

class PlaybookExecution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    playbook_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=get_utc_now)
    completed_at = db.Column(db.DateTime(timezone=True))
    result = db.Column(db.Text)
    cluster_id = db.Column(db.Integer, db.ForeignKey('cluster.id'), nullable=False)
