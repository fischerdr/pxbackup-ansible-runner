#!/bin/bash

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Setting up PX-Backup Ansible Runner development environment...${NC}\n"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed. Aborting." >&2; exit 1; }
command -v kind >/dev/null 2>&1 || { echo "Kind is required but not installed. Aborting." >&2; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "Kubectl is required but not installed. Aborting." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed. Aborting." >&2; exit 1; }

# Setup Python virtual environment
echo -e "\n${YELLOW}Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# Create Kind cluster if it doesn't exist
echo -e "\n${YELLOW}Creating Kind cluster...${NC}"
if ! kind get clusters | grep -q "pxbackup-local"; then
    kind create cluster --name pxbackup-local --config kind/config.yaml
    kubectl cluster-info --context kind-pxbackup-local
else
    echo "Kind cluster 'pxbackup-local' already exists"
    kubectl cluster-info --context kind-pxbackup-local
fi

# Create namespace
echo -e "\n${YELLOW}Creating namespace...${NC}"
kubectl create namespace pxbackup --dry-run=client -o yaml | kubectl apply -f -

# Build and load Flask application image
echo -e "\n${YELLOW}Building Flask application image...${NC}"
docker build -t pxbackup-flask:dev .
kind load docker-image pxbackup-flask:dev --name pxbackup-local

# Deploy services
echo -e "\n${YELLOW}Deploying services...${NC}"
services=(
    "postgres"
    "redis"
    "vault"
    "keycloak"
    "gitea"
    "mock-inventory"
    "prometheus"
    "flask-app"
)

for service in "${services[@]}"; do
    echo "Deploying $service..."
    kubectl apply -f k8s/dev/$service.yaml
done

# Wait for services to be ready
echo -e "\n${YELLOW}Waiting for services to be ready...${NC}"
for service in "${services[@]}"; do
    echo "Waiting for $service..."
    kubectl wait --for=condition=ready pod -l app=$service --timeout=180s
done

# Initialize database
echo -e "\n${YELLOW}Initializing database...${NC}"
kubectl exec -it $(kubectl get pod -l app=postgres -o jsonpath="{.items[0].metadata.name}") -- \
    psql -U pxbackup -d pxbackup -c "SELECT 1" || \
    kubectl exec -it $(kubectl get pod -l app=postgres -o jsonpath="{.items[0].metadata.name}") -- \
    psql -U pxbackup -d postgres -c "CREATE DATABASE pxbackup"

# Initialize Keycloak
echo -e "\n${YELLOW}Initializing Keycloak...${NC}"
KEYCLOAK_POD=$(kubectl get pod -l app=keycloak -o jsonpath="{.items[0].metadata.name}")
kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin \
    --password admin

kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh create realms \
    -s realm=pxbackup \
    -s enabled=true \
    -s displayName="PX-Backup" || true

# Initialize Vault if needed
echo -e "\n${YELLOW}Initializing Vault...${NC}"
if ! kubectl exec -it vault-0 -- vault status &> /dev/null; then
    echo "Initializing Vault..."
    kubectl exec -it vault-0 -- vault operator init
fi

echo -e "\n${GREEN}Setup complete! Services are available at:${NC}"
echo "- Flask Application: http://localhost:30500"
echo "- PostgreSQL: localhost:30432"
echo "- Keycloak: http://localhost:30080"
echo "- Vault: http://localhost:30200"
echo "- Gitea: http://localhost:30300"
echo "- Mock Inventory: http://localhost:30800"
echo "- Prometheus: http://localhost:30900"
echo "- Redis: localhost:30379"

echo -e "\n${YELLOW}Running database migrations...${NC}"
export FLASK_APP=app
kubectl exec -it $(kubectl get pod -l app=flask-app -o jsonpath="{.items[0].metadata.name}") -- \
    flask db upgrade

echo -e "\n${GREEN}Development environment is ready!${NC}"
