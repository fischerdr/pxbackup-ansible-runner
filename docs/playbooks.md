# Ansible Playbooks

## Overview

The PX-Backup Ansible Runner uses a set of playbooks to manage Kubernetes cluster integration. These playbooks handle:
- Creating service accounts
- Setting up RBAC roles
- Managing cluster access
- Validating cluster configuration

## Playbook Structure

```
playbooks/
├── cluster/
│   ├── create.yml          # Create new cluster integration
│   ├── update.yml          # Update cluster configuration
│   └── validate.yml        # Validate cluster setup
├── service-account/
│   ├── create.yml          # Create service account
│   ├── update.yml          # Update service account
│   └── delete.yml          # Delete service account
├── rbac/
│   ├── roles.yml           # Define RBAC roles
│   └── bindings.yml        # Create role bindings
└── inventory/
    └── cluster.yml         # Dynamic inventory configuration
```

## Variables

### Required Variables

```yaml
# Cluster Information
cluster_name: string
cluster_namespace: string
service_account_name: string

# Authentication
kubeconfig: string (base64 encoded)
vault_path: string
```

### Optional Variables

```yaml
# Resource Configuration
resource_prefix: string (default: pxbackup)
timeout: integer (default: 300)
verify_ssl: boolean (default: true)

# Labels and Annotations
labels:
  app: string
  environment: string
annotations:
  description: string
```

## Example Playbook

```yaml
---
- name: Create PX-Backup Cluster Integration
  hosts: localhost
  gather_facts: false

  vars:
    cluster_name: "{{ cluster_name }}"
    namespace: "{{ namespace }}"
    service_account: "{{ service_account }}"

  tasks:
    - name: Create Namespace
      kubernetes.core.k8s:
        state: present
        definition:
          apiVersion: v1
          kind: Namespace
          metadata:
            name: "{{ namespace }}"

    - name: Create Service Account
      kubernetes.core.k8s:
        state: present
        definition:
          apiVersion: v1
          kind: ServiceAccount
          metadata:
            name: "{{ service_account }}"
            namespace: "{{ namespace }}"

    - name: Create RBAC Role
      kubernetes.core.k8s:
        state: present
        definition:
          apiVersion: rbac.authorization.k8s.io/v1
          kind: ClusterRole
          metadata:
            name: "pxbackup-{{ cluster_name }}"
          rules:
            - apiGroups: ["*"]
              resources: ["*"]
              verbs: ["get", "list", "watch"]

    - name: Create Role Binding
      kubernetes.core.k8s:
        state: present
        definition:
          apiVersion: rbac.authorization.k8s.io/v1
          kind: ClusterRoleBinding
          metadata:
            name: "pxbackup-{{ cluster_name }}"
          subjects:
            - kind: ServiceAccount
              name: "{{ service_account }}"
              namespace: "{{ namespace }}"
          roleRef:
            kind: ClusterRole
            name: "pxbackup-{{ cluster_name }}"
            apiGroup: rbac.authorization.k8s.io
```

## Security Considerations

1. **Service Account Permissions**
   - Use principle of least privilege
   - Only grant necessary RBAC permissions
   - Regularly audit role bindings

2. **Secret Management**
   - Store sensitive data in Vault
   - Rotate service account tokens regularly
   - Use secure communication channels

3. **Validation**
   - Validate cluster accessibility
   - Check required API endpoints
   - Verify RBAC permissions

## Best Practices

1. **Idempotency**
   - All playbooks should be idempotent
   - Use `state: present` for resources
   - Check existing resources before creation

2. **Error Handling**
   - Include proper error messages
   - Handle timeouts gracefully
   - Implement retries for transient failures

3. **Documentation**
   - Comment complex tasks
   - Document required variables
   - Include usage examples

4. **Testing**
   - Test playbooks in development environment
   - Validate against different Kubernetes versions
   - Include cleanup tasks

## Troubleshooting

Common issues and solutions:

1. **Permission Denied**
   - Verify RBAC configuration
   - Check service account token
   - Validate cluster access

2. **Resource Creation Failure**
   - Check namespace exists
   - Verify resource quotas
   - Review API server logs

3. **Timeout Issues**
   - Increase timeout values
   - Check network connectivity
   - Verify cluster health

## Integration Testing

Test playbooks using:

```bash
# Test specific playbook
ansible-playbook playbooks/cluster/create.yml -e @vars.yml

# Validate configuration
ansible-playbook playbooks/cluster/validate.yml -e @vars.yml

# Run with debug output
ansible-playbook playbooks/cluster/create.yml -e @vars.yml -vvv
```
