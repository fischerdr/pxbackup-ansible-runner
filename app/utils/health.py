"""Health check utilities."""

from typing import Dict, Any
import aiohttp
from sqlalchemy.sql import text
from flask import current_app
import hvac
from datetime import datetime, timezone

async def check_database_health() -> bool:
    """Check database connectivity."""
    try:
        from .. import db
        result = await db.session.execute(text('SELECT 1'))
        return bool(result.scalar())
    except Exception:
        return False

async def check_vault_health() -> bool:
    """Check Vault connectivity and status."""
    try:
        client = hvac.Client(
            url=current_app.config['VAULT_ADDR'],
            token=current_app.config['VAULT_TOKEN']
        )
        return client.sys.is_initialized() and not client.sys.is_sealed()
    except Exception:
        return False

async def check_kubernetes_health() -> bool:
    """Check Kubernetes API connectivity."""
    try:
        api_url = current_app.config['K8S_API_URL']
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}/healthz") as response:
                return response.status == 200
    except Exception:
        return False

async def get_system_health() -> Dict[str, Any]:
    """Get comprehensive system health status."""
    checks = {
        'database': await check_database_health(),
        'vault': await check_vault_health(),
        'kubernetes': await check_kubernetes_health()
    }
    
    return {
        'status': 'healthy' if all(checks.values()) else 'unhealthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'checks': checks,
        'details': {
            'database': {
                'status': 'up' if checks['database'] else 'down',
                'type': current_app.config['SQLALCHEMY_DATABASE_URI'].split('://')[0]
            },
            'vault': {
                'status': 'up' if checks['vault'] else 'down',
                'address': current_app.config['VAULT_ADDR']
            },
            'kubernetes': {
                'status': 'up' if checks['kubernetes'] else 'down',
                'api_url': current_app.config['K8S_API_URL']
            }
        }
    }
