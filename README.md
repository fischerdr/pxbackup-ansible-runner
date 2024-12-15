# PX-Backup Ansible Runner

[![Test and Lint](https://github.com/portworx/pxbackup-ansible-runner/actions/workflows/test.yml/badge.svg)](https://github.com/portworx/pxbackup-ansible-runner/actions/workflows/test.yml)
[![Docker Build](https://github.com/portworx/pxbackup-ansible-runner/actions/workflows/docker.yml/badge.svg)](https://github.com/portworx/pxbackup-ansible-runner/actions/workflows/docker.yml)
[![Code Coverage](https://codecov.io/gh/portworx/pxbackup-ansible-runner/branch/main/graph/badge.svg)](https://codecov.io/gh/portworx/pxbackup-ansible-runner)

A Flask-based microservice that manages Kubernetes cluster integration with PX-Backup through Ansible playbooks. This service handles:
- Adding new clusters to PX-Backup
- Updating service account credentials
- Managing cluster authentication
- Monitoring cluster connectivity

## Features

- **Automated Cluster Integration**: Streamlined process for adding Kubernetes clusters to PX-Backup
- **Service Account Management**: Automated creation and renewal of Kubernetes service accounts
- **Security First**: Built-in authentication, authorization, and secure secret management
- **Monitoring & Metrics**: Prometheus metrics for operation tracking and monitoring
- **Scalable Architecture**: Designed to handle multiple clusters and concurrent operations
- **Audit Logging**: Comprehensive logging of all operations for compliance and debugging

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   PX-Backup     │────▶│ Ansible      │────▶│ Kubernetes  │
│   API Server    │     │ Runner       │     │ Clusters    │
└─────────────────┘     └──────────────┘     └─────────────┘
         │                     │                    ▲
         │                     │                    │
         ▼                     ▼                    │
┌─────────────────┐     ┌──────────────┐          │
│     Vault       │     │   Playbook   │          │
│  (Secrets)      │     │ Repository   │──────────┘
└─────────────────┘     └──────────────┘
```

## Prerequisites

- Python 3.11 or higher
- Docker and Kind (for local development)
- Kubernetes cluster
- Vault instance
- Redis (for caching and rate limiting)

## Installation

### Using Docker

```bash
docker pull ghcr.io/portworx/pxbackup-ansible-runner:latest

docker run -d \
  -p 5000:5000 \
  -e VAULT_ADDR=http://vault:8200 \
  -e VAULT_TOKEN=<token> \
  -e KEYCLOAK_URL=http://keycloak:8080 \
  ghcr.io/portworx/pxbackup-ansible-runner:latest
```

### From Source

```bash
# Clone the repository
git clone https://github.com/portworx/pxbackup-ansible-runner.git
cd pxbackup-ansible-runner

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
flask run
```

## Configuration

The service is configured through environment variables:

```bash
# Core Settings
FLASK_APP=app
FLASK_ENV=production
SQLALCHEMY_DATABASE_URI=sqlite:///app.db

# Authentication
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=pxbackup
KEYCLOAK_CLIENT_ID=pxbackup-client
KEYCLOAK_CLIENT_SECRET=<secret>

# External Services
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=<token>
REDIS_URL=redis://redis:6379/0
GITEA_URL=http://gitea:3000
GITEA_PLAYBOOKS_REPO=pxbackup/playbooks
```

## API Endpoints

### Cluster Management

#### Add New Cluster
```http
POST /api/v1/clusters
Content-Type: application/json
Authorization: Bearer <token>

{
    "name": "production-cluster",
    "kubeconfig": "base64-encoded-kubeconfig",
    "service_account": "pxbackup-sa",
    "namespace": "pxbackup-system"
}
```

#### Update Service Account
```http
POST /api/v1/clusters/{name}/service-account
Content-Type: application/json
Authorization: Bearer <token>

{
    "service_account": "new-sa",
    "namespace": "new-namespace"
}
```

#### Check Cluster Status
```http
GET /api/v1/clusters/{name}/status
Authorization: Bearer <token>
```

### Monitoring

#### Health Check
```http
GET /api/v1/health
```

#### Metrics
```http
GET /metrics
```

## Development

See [Local Development Guide](docs/local_development.md) for detailed setup instructions.

```bash
# Start development environment
./scripts/setup_dev.sh

# Run tests
pytest

# Run linting
black app tests
flake8 app tests
mypy app tests

# Clean up
./scripts/cleanup_dev.sh
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test types
pytest -m unit
pytest -m integration
```

## Security

- All endpoints require authentication via JWT tokens
- Secrets are stored in Vault
- Service accounts follow principle of least privilege
- Regular security scanning of dependencies and container images
- Comprehensive audit logging

## Metrics

The service exposes Prometheus metrics at `/metrics`:

- `http_requests_total`: Total HTTP requests by endpoint and status
- `playbook_execution_duration_seconds`: Ansible playbook execution duration
- `vault_operation_duration_seconds`: Vault operation latency
- `cluster_operations_total`: Total cluster operations by type and status

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

Apache License 2.0

## Support

For support, please:
1. Check the [documentation](docs/)
2. Open an issue
3. Contact Portworx support
