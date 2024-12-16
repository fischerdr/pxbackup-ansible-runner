# Local Development Environment

This directory contains Kubernetes manifests for setting up a local development environment for the PX-Backup Ansible Runner.

## Prerequisites

- Kubernetes cluster (minikube, kind, or k3d)
- kubectl
- kustomize

## Components

- Flask Application (port 30500)
- PostgreSQL Database
- Redis for distributed locking
- Vault for secrets management
- Keycloak for authentication
- Gitea for playbook storage
- Mock Inventory Service for testing
- Prometheus for monitoring

## Quick Start

1. Create the development namespace:
   ```bash
   kubectl apply -f namespace.yaml
   ```

2. Deploy all components:
   ```bash
   kubectl apply -k .
   ```

3. Access the application:
   ```bash
   curl http://localhost:30500/health
   ```

## Development Tips

- All services are configured for local development with debug modes enabled
- Database credentials and other secrets are simplified for development
- Services are accessible within the cluster using their service names
- The Flask application is exposed via NodePort 30500
