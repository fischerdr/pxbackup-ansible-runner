# Local Development Guide

This guide explains how to set up a local development environment for the PX-Backup Ansible Runner application.

## Prerequisites

- Docker
- Kind (Kubernetes in Docker)
- kubectl
- Python 3.11 or higher
- Git

## Quick Start

The easiest way to get started is using our automated setup script:

```bash
# Start the development environment
./scripts/setup_dev.sh

# When done, clean up the environment
./scripts/cleanup_dev.sh
```

The setup script will:
1. Create a Kind cluster
2. Deploy all required services
3. Build and deploy the Flask application
4. Set up port forwarding
5. Initialize all services with test data

After setup completes, the application will be available at http://localhost:5000.

## Manual Setup

If you prefer to set up the environment manually, follow these steps:

### 1. Create Kind Cluster

```bash
kind create cluster --name pxbackup --config kind/cluster-config.yaml
```

### 2. Build Flask Application

```bash
# Build Docker image
docker build -t pxbackup-flask:dev .

# Load image into Kind
kind load docker-image pxbackup-flask:dev --name pxbackup
```

### 3. Deploy Services

```bash
# Create namespace
kubectl create namespace pxbackup

# Deploy core services
kubectl apply -f k8s/dev/redis.yaml
kubectl apply -f k8s/dev/vault.yaml
kubectl apply -f k8s/dev/mock-inventory.yaml
kubectl apply -f k8s/dev/keycloak.yaml
kubectl apply -f k8s/dev/gitea.yaml
kubectl apply -f k8s/dev/prometheus.yaml
kubectl apply -f k8s/dev/flask-app.yaml

# Wait for services to be ready
kubectl wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl wait --for=condition=ready pod -l app=vault --timeout=120s
kubectl wait --for=condition=ready pod -l app=mock-inventory --timeout=120s
kubectl wait --for=condition=ready pod -l app=keycloak --timeout=180s
kubectl wait --for=condition=ready pod -l app=gitea --timeout=180s
kubectl wait --for=condition=ready pod -l app=prometheus --timeout=120s
kubectl wait --for=condition=ready pod -l app=flask-app --timeout=180s
```

### 4. Set Up Port Forwarding

```bash
kubectl port-forward svc/flask-app 5000:5000
```

### 5. Initialize Services

#### Keycloak Setup
```bash
# Get Keycloak pod name
KEYCLOAK_POD=$(kubectl get pod -l app=keycloak -o jsonpath="{.items[0].metadata.name}")

# Configure realm and user
kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin \
    --password admin

kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh create realms \
    -s realm=pxbackup \
    -s enabled=true

kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh create users \
    -r pxbackup \
    -s username=testuser \
    -s enabled=true \
    -s email=testuser@example.com
```

#### Gitea Setup
```bash
# Get Gitea pod name
GITEA_POD=$(kubectl get pod -l app=gitea -o jsonpath="{.items[0].metadata.name}")

# Create test user and repository
kubectl exec $GITEA_POD -- su git -c "gitea admin user create \
    --username testuser \
    --password testpass \
    --email testuser@example.com \
    --admin"

kubectl exec $GITEA_POD -- su git -c "gitea admin create-repo \
    --name pxbackup-playbooks \
    --owner testuser"
```

## Development Workflow

### Running Tests
```bash
# Run unit tests
pytest tests/unit

# Run integration tests
pytest tests/integration

# Run with coverage
pytest --cov=app tests/
```

### Making Code Changes

The Flask application runs in the Kind cluster, but the code is mounted as a volume for development. When you make code changes:

1. The changes will be reflected in the container
2. Gunicorn will automatically reload the application

### Accessing Services

- Flask Application: http://localhost:5000
- Keycloak Admin: http://localhost:8080
- Gitea: http://localhost:3000
- Prometheus: http://localhost:9090
- Vault: http://localhost:8200

### Test Credentials

- **Keycloak**:
  - Username: testuser
  - Password: testpass
  - Realm: pxbackup

- **Gitea**:
  - Username: testuser
  - Password: testpass

## Troubleshooting

### Common Issues

1. **Pod Startup Issues**
   ```bash
   # Check pod status
   kubectl get pods
   
   # View pod logs
   kubectl logs <pod-name>
   ```

2. **Service Connection Issues**
   ```bash
   # Check service status
   kubectl get svc
   
   # Test service connectivity
   kubectl port-forward svc/<service-name> <local-port>:<service-port>
   ```

3. **Flask App Issues**
   ```bash
   # View Flask app logs
   kubectl logs -l app=flask-app
   
   # Restart Flask app
   kubectl rollout restart deployment/flask-app
   ```

## Cleanup

To clean up the development environment:

```bash
# Using cleanup script (recommended)
./scripts/cleanup_dev.sh

# Manual cleanup
kind delete cluster --name pxbackup
docker rmi pxbackup-flask:dev
```

## Architecture

The local development environment consists of:
- Kind Kubernetes cluster
- Flask application running in the cluster
- SQLite database for persistent storage
- Redis for caching and rate limiting
- Vault for secrets management
- Keycloak for authentication
- Gitea for playbook storage
- Prometheus for metrics
- Mock Inventory service for testing

## Security Notes

The development environment uses insecure defaults:
- Self-signed certificates
- Default credentials
- Development mode settings

**DO NOT** use these settings in production.
