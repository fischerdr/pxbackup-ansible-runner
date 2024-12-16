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

# Install metrics-server for HPA
echo -e "\n${YELLOW}Installing metrics-server...${NC}"
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# Patch metrics-server to work with Kind's self-signed certificates
kubectl patch -n kube-system deployment metrics-server --type=json -p='[{"op": "add", "path": "/spec/template/spec/containers/0/args/-", "value": "--kubelet-insecure-tls"}]'

# Create namespace
echo -e "\n${YELLOW}Creating namespace...${NC}"
kubectl create namespace pxbackup --dry-run=client -o yaml | kubectl apply -f -

# Build and load Flask application image
echo -e "\n${YELLOW}Building Flask application image...${NC}"
docker build -t pxbackup-flask:dev .
kind load docker-image pxbackup-flask:dev --name pxbackup-local

# Deploy all services using kustomization
echo -e "\n${YELLOW}Deploying services using kustomization...${NC}"
kubectl apply -k k8s/dev/

# Wait for core services to be ready
echo -e "\n${YELLOW}Waiting for services to be ready...${NC}"
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
    echo "Waiting for $service..."
    kubectl wait --for=condition=ready pod -l app=$service --timeout=180s
done

# Initialize database
echo -e "\n${YELLOW}Initializing database...${NC}"
POSTGRES_POD=$(kubectl get pod -l app=postgres -o jsonpath="{.items[0].metadata.name}")
kubectl exec -it $POSTGRES_POD -- \
    psql -U pxbackup -d postgres -c "CREATE DATABASE pxbackup" || true

# Run database migrations
echo -e "\n${YELLOW}Running database migrations...${NC}"
export FLASK_APP=app
kubectl exec -it $(kubectl get pod -l app=flask-app -o jsonpath="{.items[0].metadata.name}") -- \
    flask db upgrade

# Initialize Vault
echo -e "\n${YELLOW}Initializing Vault...${NC}"
VAULT_POD="vault-0"
if ! kubectl exec -it $VAULT_POD -- vault status &> /dev/null; then
    echo "Initializing Vault..."
    # Initialize and capture keys/token
    kubectl exec -it $VAULT_POD -- vault operator init > vault-keys.txt
    # Unseal using first 3 keys
    for i in {1..3}; do
        KEY=$(grep "Unseal Key $i:" vault-keys.txt | cut -d: -f2 | tr -d ' ')
        kubectl exec -it $VAULT_POD -- vault operator unseal $KEY
    done
    # Login with root token
    ROOT_TOKEN=$(grep "Initial Root Token:" vault-keys.txt | cut -d: -f2 | tr -d ' ')
    kubectl exec -it $VAULT_POD -- vault login $ROOT_TOKEN

    # Enable required secrets engines
    kubectl exec -it $VAULT_POD -- vault secrets enable -path=pxbackup kv-v2

    # Store development secrets
    kubectl exec -it $VAULT_POD -- vault kv put pxbackup/dev/kubeconfig \
        value="$(cat ~/.kube/config | base64)"
fi

# Initialize Keycloak
echo -e "\n${YELLOW}Initializing Keycloak...${NC}"
KEYCLOAK_POD=$(kubectl get pod -l app=keycloak -o jsonpath="{.items[0].metadata.name}")
kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin \
    --password admin

# Create realm and client
kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh create realms \
    -s realm=pxbackup \
    -s enabled=true \
    -s displayName="PX-Backup" || true

kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh create clients \
    -r pxbackup \
    -s clientId=pxbackup-client \
    -s enabled=true \
    -s clientAuthenticatorType=client-secret \
    -s secret=pxbackup-secret \
    -s 'redirectUris=["http://localhost:30500/*"]' \
    -s 'webOrigins=["http://localhost:30500"]' || true

# Initialize Gitea with playbook repository
echo -e "\n${YELLOW}Initializing Gitea...${NC}"
GITEA_POD=$(kubectl get pod -l app=gitea -o jsonpath="{.items[0].metadata.name}")
kubectl exec -it $GITEA_POD -- su git -c "gitea admin user create --username admin --password admin123 --email admin@example.com --must-change-password=false" || true
kubectl exec -it $GITEA_POD -- su git -c "gitea admin user create --username pxbackup --password pxbackup123 --email pxbackup@example.com --must-change-password=false" || true

# Create and populate playbook repository
kubectl exec -it $GITEA_POD -- su git -c "gitea admin create-repo --name pxbackup-playbooks --user pxbackup" || true

# Initialize mock inventory with sample data
echo -e "\n${YELLOW}Initializing mock inventory...${NC}"
MOCK_POD=$(kubectl get pod -l app=mock-inventory -o jsonpath="{.items[0].metadata.name}")
kubectl exec -it $MOCK_POD -- curl -X POST http://localhost:8080/clusters \
    -H "Content-Type: application/json" \
    -d '{"name":"test-cluster","kubeconfig":"dummy","status":"active"}' || true

# Wait for HPA to be ready
echo -e "\n${YELLOW}Waiting for HPA to be ready...${NC}"
kubectl wait --for=condition=ready hpa/flask-app-hpa --timeout=60s || echo "Warning: HPA not ready yet"

echo -e "\n${GREEN}Setup complete! Services are available at:${NC}"
echo "- Flask Application: http://localhost:30500"
echo "- PostgreSQL: localhost:30432"
echo "- Keycloak: http://localhost:30080"
echo "- Vault: http://localhost:30200"
echo "- Gitea: http://localhost:30300"
echo "- Mock Inventory: http://localhost:30800"
echo "- Prometheus: http://localhost:30900"
echo "- Redis: localhost:30379"

echo -e "\n${YELLOW}Development credentials:${NC}"
echo "Keycloak:"
echo "  - Admin: admin/admin"
echo "  - Client ID: pxbackup-client"
echo "  - Client Secret: pxbackup-secret"
echo "Gitea:"
echo "  - Admin: admin/admin123"
echo "  - Service: pxbackup/pxbackup123"
echo "PostgreSQL:"
echo "  - User: pxbackup"
echo "  - Password: pxbackup"
echo "Vault:"
echo "  - Root token and unseal keys saved in vault-keys.txt"

echo -e "\n${GREEN}Development environment is ready!${NC}"
