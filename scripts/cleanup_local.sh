#!/bin/bash

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Cleaning up PX-Backup Ansible Runner development environment...${NC}\n"

# Function to check if a command exists
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is required but not installed.${NC}"
        exit 1
    fi
}

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"
check_command "docker"
check_command "kind"
check_command "kubectl"

# Function to safely delete k8s resources
safe_delete() {
    local resource=$1
    local name=$2
    if kubectl get $resource $name &>/dev/null; then
        echo "Deleting $resource $name..."
        kubectl delete $resource $name --timeout=60s || true
    fi
}

# Function to wait for pod deletion
wait_for_pod_deletion() {
    local label=$1
    local timeout=60
    local count=0

    while kubectl get pod -l app=$label &>/dev/null && [ $count -lt $timeout ]; do
        echo "Waiting for $label pods to terminate..."
        sleep 1
        ((count++))
    done
}

# Save vault keys if they exist
if [ -f "vault-keys.txt" ]; then
    echo -e "\n${YELLOW}Backing up Vault keys...${NC}"
    cp vault-keys.txt vault-keys.backup.txt
fi

# Delete all resources in reverse order of creation
echo -e "\n${YELLOW}Removing Kubernetes resources...${NC}"

# Delete HPA first to stop auto-scaling
safe_delete "hpa" "flask-app"

# Delete all resources using kustomization
if [ -d "k8s/dev" ]; then
    echo "Removing all dev resources..."
    kubectl delete -k k8s/dev/ --timeout=120s || true
fi

# Wait for critical pods to terminate
services=(
    "flask-app"
    "postgres"
    "redis"
    "vault"
    "keycloak"
    "gitea"
    "mock-inventory"
    "prometheus"
)

for service in "${services[@]}"; do
    wait_for_pod_deletion $service
done

# Remove namespace
echo -e "\n${YELLOW}Removing namespace...${NC}"
safe_delete "namespace" "pxbackup"

# Remove metrics server
echo -e "\n${YELLOW}Removing metrics-server...${NC}"
kubectl delete -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml || true

# Delete Kind cluster
echo -e "\n${YELLOW}Deleting Kind cluster...${NC}"
if kind get clusters | grep -q "pxbackup-local"; then
    kind delete cluster --name pxbackup-local
fi

# Clean up Docker images
echo -e "\n${YELLOW}Cleaning up Docker images...${NC}"
docker rmi pxbackup-flask:dev || true

# Clean up Python virtual environment
echo -e "\n${YELLOW}Cleaning up Python virtual environment...${NC}"
if [ -d "venv" ]; then
    rm -rf venv
fi

# Clean up any remaining files
echo -e "\n${YELLOW}Cleaning up temporary files...${NC}"
rm -f vault-keys.txt

echo -e "\n${GREEN}Cleanup completed successfully!${NC}"
if [ -f "vault-keys.backup.txt" ]; then
    echo -e "${YELLOW}Note: Vault keys have been backed up to vault-keys.backup.txt${NC}"
fi
