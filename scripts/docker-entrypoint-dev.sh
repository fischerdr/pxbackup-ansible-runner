#!/bin/bash
set -e

# Function to wait for a service to be ready
wait_for_service() {
    local host="$1"
    local port="$2"
    local service="$3"

    echo "Waiting for $service to be ready..."
    while ! nc -z "$host" "$port"; do
        sleep 1
    done
    echo "$service is ready!"
}

# Wait for required services in k8s
wait_for_service "postgres" "30432" "PostgreSQL"
wait_for_service "redis" "30379" "Redis"
wait_for_service "vault" "30200" "Vault"
wait_for_service "keycloak" "30080" "Keycloak"
wait_for_service "mock-inventory" "30800" "Mock Inventory"
wait_for_service "gitea" "30300" "Gitea"

# Run database migrations
flask db upgrade

# Start the Flask development server
# If FLASK_DEBUG_PORT is set, start with debugger
if [ ! -z "$FLASK_DEBUG_PORT" ]; then
    echo "Starting Flask with debugger on port 30500"
    python -m debugpy --listen "0.0.0.0:5678" -m flask run --host=0.0.0.0 --port=30500 --reload
else
    # Execute the CMD with the correct port
    exec flask run --host=0.0.0.0 --port=30500 "$@"
fi
