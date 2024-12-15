#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}Cleaning up PX-Backup Ansible Runner development environment...${NC}\n"

# Delete Kind cluster
echo -e "${YELLOW}Deleting Kind cluster...${NC}"
if kind get clusters | grep -q "pxbackup"; then
    kind delete cluster --name pxbackup
fi

# Clean up Python environment
echo -e "\n${YELLOW}Cleaning up Python environment...${NC}"
if [ -d "venv" ]; then
    rm -rf venv
fi

# Clean up database
echo -e "\n${YELLOW}Cleaning up database...${NC}"
if [ -d "instance" ]; then
    rm -rf instance
fi

# Stop port forwarding
echo -e "\n${YELLOW}Stopping port forwarding...${NC}"
if [ -f ".flask_pf_pid" ]; then
    kill $(cat .flask_pf_pid) 2>/dev/null || true
    rm .flask_pf_pid
fi

# Clean up Docker images
echo -e "\n${YELLOW}Cleaning up Docker images...${NC}"
docker rmi pxbackup-flask:dev 2>/dev/null || true

# Remove .env file
echo -e "\n${YELLOW}Removing .env file...${NC}"
if [ -f ".env" ]; then
    rm .env
fi

echo -e "\n${RED}Cleanup complete!${NC}"
