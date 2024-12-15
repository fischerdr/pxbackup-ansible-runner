# API Documentation

## Authentication

All API endpoints require a valid JWT token obtained from Keycloak. The token should be included in the `Authorization` header as a Bearer token.

```http
Authorization: Bearer <token>
```

## Endpoints

### Cluster Management

#### Create New Cluster

Creates a new cluster in PX-Backup and sets up the required service account. The cluster must exist in the inventory system before it can be added to PX-Backup.

```http
POST /api/v1/clusters
```

**Request Body**
```json
{
    "name": "string",
    "kubeconfig": "string (base64, optional)",
    "kubeconfig_vault_path": "string (optional)",
    "service_account": "string",
    "namespace": "string",
    "force": "boolean (optional)"
}
```

**Notes:**
- The cluster must exist in the inventory system before it can be added
- Either `kubeconfig` or `kubeconfig_vault_path` must be provided
- If both kubeconfig sources are provided, the request will be rejected
- `kubeconfig` should be base64 encoded
- `kubeconfig_vault_path` should point to a Vault secret containing a `kubeconfig` key
- `force` defaults to false. If true, will recreate the cluster if it already exists

**Response**
```json
{
    "id": "string",
    "name": "string",
    "status": "string",
    "created_at": "string (ISO 8601)",
    "updated_at": "string (ISO 8601)"
}
```

**Status Codes**
- `201`: Cluster created successfully
- `400`: Invalid request data
- `404`: Cluster not found in inventory
- `409`: Cluster already exists in PX-Backup (when force=false)
- `500`: Internal server error

#### Update Service Account

Updates the service account used by PX-Backup to connect to the cluster.

```http
POST /api/v1/clusters/{name}/service-account
```

**Path Parameters**
- `name`: Cluster name

**Request Body**
```json
{
    "service_account": "string",
    "namespace": "string"
}
```

**Response**
```json
{
    "name": "string",
    "service_account": "string",
    "namespace": "string",
    "updated_at": "string (ISO 8601)"
}
```

**Status Codes**
- `200`: Service account updated successfully
- `404`: Cluster not found
- `500`: Internal server error

#### Check Cluster Status

Retrieves the current status of a cluster.

```http
GET /api/v1/clusters/{name}/status
```

**Path Parameters**
- `name`: Cluster name

**Response**
```json
{
    "name": "string",
    "status": "string",
    "details": {
        "version": "string",
        "nodes": "integer",
        "last_check": "string (ISO 8601)"
    }
}
```

**Status Codes**
- `200`: Status retrieved successfully
- `404`: Cluster not found
- `500`: Internal server error

### Health and Monitoring

#### Health Check

Check the health of the service and its dependencies.

```http
GET /api/v1/health
```

**Response**
```json
{
    "status": "string",
    "services": {
        "vault": "string",
        "redis": "string",
        "database": "string"
    },
    "version": "string"
}
```

#### Metrics

Prometheus metrics endpoint.

```http
GET /metrics
```

**Response**
- Content-Type: text/plain
- Prometheus format metrics

## Error Responses

All error responses follow this format:

```json
{
    "error": "string",
    "message": "string",
    "details": "object (optional)"
}
```

## Rate Limiting

The API implements rate limiting based on client IP:
- 100 requests per minute for authenticated endpoints
- 10 requests per minute for authentication endpoints

## Audit Logging

All operations are logged with:
- User ID
- Action
- Timestamp
- Status
- Details
