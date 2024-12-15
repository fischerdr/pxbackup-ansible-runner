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

# Create Kind cluster
echo -e "\n${YELLOW}Creating Kind cluster...${NC}"
if kind get clusters | grep -q "pxbackup"; then
    echo "Cluster already exists, skipping creation"
else
    kind create cluster --name pxbackup --config kind/cluster-config.yaml
    kubectl cluster-info --context kind-pxbackup
fi

# Create namespace
echo -e "\n${YELLOW}Creating namespace...${NC}"
kubectl create namespace pxbackup --dry-run=client -o yaml | kubectl apply -f -

# Deploy services
echo -e "\n${YELLOW}Deploying services...${NC}"
kubectl apply -f k8s/dev/redis.yaml
kubectl apply -f k8s/dev/vault.yaml
kubectl apply -f k8s/dev/mock-inventory.yaml
kubectl apply -f k8s/dev/keycloak.yaml
kubectl apply -f k8s/dev/gitea.yaml
kubectl apply -f k8s/dev/prometheus.yaml

# Wait for services to be ready
echo -e "\n${YELLOW}Waiting for services to be ready...${NC}"
services=("redis" "vault" "mock-inventory" "keycloak" "gitea" "prometheus")
for service in "${services[@]}"; do
    echo "Waiting for $service..."
    kubectl wait --for=condition=ready pod -l app=$service --timeout=180s
done

# Build and load Flask application image
echo -e "\n${YELLOW}Building Flask application image...${NC}"
docker build -t pxbackup-flask:dev .
kind load docker-image pxbackup-flask:dev --name pxbackup

# Update Flask app deployment image
echo -e "\n${YELLOW}Updating Flask app deployment...${NC}"
sed -i 's|image: python:3.11-slim|image: pxbackup-flask:dev|g' k8s/dev/flask-app.yaml

# Deploy Flask application
echo -e "\n${YELLOW}Deploying Flask application...${NC}"
kubectl apply -f k8s/dev/flask-app.yaml

# Wait for Flask app to be ready
echo -e "\n${YELLOW}Waiting for Flask application to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app=flask-app --timeout=180s

# Port forward Flask application
echo -e "\n${YELLOW}Setting up port forwarding...${NC}"
kubectl port-forward svc/flask-app 5000:5000 &
FLASK_PF_PID=$!

# Save port forward PID for cleanup
echo $FLASK_PF_PID > .flask_pf_pid

echo -e "\n${GREEN}Flask application is running!${NC}"
echo -e "Access the application at: http://localhost:5000"
echo -e "To stop port forwarding, run: kill $(cat .flask_pf_pid)"

# Setup Python virtual environment
echo -e "\n${YELLOW}Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# Create instance directory and initialize database
echo -e "\n${YELLOW}Initializing database...${NC}"
mkdir -p instance
export FLASK_APP=app
flask db upgrade

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
    -s sslRequired=none

kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh create users \
    -r pxbackup \
    -s username=testuser \
    -s enabled=true \
    -s email=testuser@example.com \
    -s firstName=Test \
    -s lastName=User

kubectl exec $KEYCLOAK_POD -- /opt/keycloak/bin/kcadm.sh set-password \
    -r pxbackup \
    --username testuser \
    --new-password testpass

# Initialize Gitea
echo -e "\n${YELLOW}Initializing Gitea...${NC}"
GITEA_POD=$(kubectl get pod -l app=gitea -o jsonpath="{.items[0].metadata.name}")
kubectl exec $GITEA_POD -- su git -c "gitea admin user create \
    --username testuser \
    --password testpass \
    --email testuser@example.com \
    --admin"

kubectl exec $GITEA_POD -- su git -c "gitea admin create-repo \
    --name pxbackup-playbooks \
    --owner testuser \
    --private=false"

# Create .env file
echo -e "\n${YELLOW}Creating .env file...${NC}"
cat > .env << EOL
# Flask Settings
FLASK_APP=app
FLASK_ENV=development
FLASK_DEBUG=1

# Database
DATABASE_URL=sqlite:///instance/app.db

# Redis
REDIS_URL=redis://localhost:6379/0

# Vault
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=root
VAULT_NAMESPACE=default

# Mock Inventory
INVENTORY_API_URL=http://localhost:8080

# Keycloak
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=pxbackup
KEYCLOAK_CLIENT_ID=pxbackup-client
KEYCLOAK_CLIENT_SECRET=pxbackup-secret

# Gitea
GITEA_URL=http://localhost:3000
GITEA_PLAYBOOKS_REPO=testuser/pxbackup-playbooks

# Prometheus
PROMETHEUS_URL=http://localhost:9090
EOL

echo -e "\n${GREEN}Setup complete! You can now start the application with:${NC}"
echo -e "source venv/bin/activate"
echo -e "flask run --host=0.0.0.0 --port=5000"
