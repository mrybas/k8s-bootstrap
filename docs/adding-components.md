# Adding New Components

This guide explains how to add new Helm chart components to k8s-bootstrap.

**No local dependencies needed** - the generator runs in Docker.

## Quick Start

```bash
# Interactive mode (recommended for first time)
make add-component

# Quick mode with arguments
make add-component-quick \
  REPO=https://kubernetes-sigs.github.io/external-dns/ \
  CHART=external-dns \
  VERSION=1.14.3

# List available categories
./scripts/add-component.sh --list-categories

# Show component architecture (operators/instances)
python scripts/update-chart-versions.py --architecture
```

## Component Definition Structure

Each component is defined in `backend/definitions/components/<id>.yaml`:

```yaml
# Required fields
id: my-component           # Unique identifier (used in URLs, filenames)
name: My Component         # Display name
description: Description   # Short description
category: system           # Category (see below)

# Chart configuration
chartType: upstream        # "upstream", "custom", or "meta"
namespace: my-component    # Target namespace
releaseName: my-component  # Helm release name

# Upstream chart source
upstream:
  repository: https://charts.example.com
  chartName: my-chart
  version: "1.0.0"

# Optional: Dependencies
dependsOn:
  - namespaces            # Wait for namespaces
  - some-crds             # Wait for CRDs

# Optional: Auto-include when another component is selected
autoInclude:
  when: [parent-component]

# Default Helm values
defaultValues:
  replicaCount: 1

# JSON Schema for UI form
jsonSchema:
  type: object
  properties:
    replicaCount:
      type: integer
      title: Replicas
      default: 1

# UI hints
uiSchema:
  resources:
    ui:collapsed: true
```

## Component Types

### Standard Component

Regular Helm chart:

```yaml
id: metrics-server
chartType: upstream
category: system
```

### CRD Component (Hidden)

CRD-only charts that are auto-included:

```yaml
id: cert-manager-crds
hidden: true
category: crds
autoInclude:
  when: [cert-manager]  # Auto-include when cert-manager selected
```

### Operator Component

Operators that manage instances:

```yaml
id: grafana-operator
isOperator: true
category: observability
```

### Multi-Instance Component

Components deployable multiple times:

```yaml
id: grafana-instance
multiInstance: true
requiresOperator: grafana-operator
defaultNamespace: monitoring
```

### Dependent Component (Single Instance)

Components that depend on another component but are not multi-instance:

```yaml
id: metallb-config
name: MetalLB Configuration
requiresOperator: metallb   # Blocked in UI until metallb is selected
dependsOn:
  - metallb                 # Flux dependency for installation order
chartType: custom
```

This pattern is used when:
- A configuration component depends on a main component (e.g., metallb-config → metallb)
- The component should be blocked in UI until its dependency is selected
- Only one instance is needed (not multi-instance)

In the UI, the component will show "🔒 Select metallb first" until the dependency is selected.

### Meta-Component

Logical grouping that auto-includes sub-components:

```yaml
id: istio
chartType: meta
autoIncludes:
  - istio-base
  - istiod
  - istio-gateway
```

## Using the Generator

### Interactive Mode

```bash
make add-component
```

The generator will:
1. Ask for component ID, repository URL, chart name, version
2. **Auto-detect** if it's an operator or multi-instance component
3. Fetch chart's `values.yaml` from Helm repo
4. Auto-generate JSON schema from values
5. Create the component definition file

### CLI Mode

```bash
./scripts/add-component.sh \
  --id external-dns \
  --repo https://kubernetes-sigs.github.io/external-dns/ \
  --chart external-dns \
  --version 1.14.3 \
  --category system \
  --docs-url https://github.com/kubernetes-sigs/external-dns

# For operators
./scripts/add-component.sh \
  --id my-operator \
  --repo https://... \
  --operator

# For multi-instance components
./scripts/add-component.sh \
  --id my-instance \
  --repo https://... \
  --multi-instance \
  --requires-operator my-operator
```

### Options

| Option | Description |
|--------|-------------|
| `--id` | Component ID (required) |
| `--repo` | Helm repository URL (required) |
| `--chart` | Chart name (default: same as id) |
| `--version` | Chart version |
| `--category` | Category (see below) |
| `--name` | Display name |
| `--namespace` | Kubernetes namespace |
| `--docs-url` | Documentation URL |
| `--operator` | Mark as operator component |
| `--multi-instance` | Mark as multi-instance |
| `--requires-operator` | Component/operator this component requires (blocks UI selection) |
| `--no-fetch` | Don't fetch values.yaml |
| `--output` | Custom output path |
| `--print` | Print to stdout |

## Categories

Categories are defined in `backend/definitions/categories.yaml`:

```yaml
categories:
  core:
    name: Core
    icon: "🎯"
    description: Core Flux components
    priority: 10
  
  crds:
    name: CRDs
    icon: "📋"
    description: Custom Resource Definitions
    priority: 20
  
  system:
    name: System
    icon: "⚙️"
    description: Core system components
    priority: 30
  
  ingress:
    name: Ingress
    icon: "🌐"
    description: Ingress controllers
    priority: 40
  
  security:
    name: Security
    icon: "🔐"
    description: Security components
    priority: 50
  
  storage:
    name: Storage
    icon: "💾"
    description: Storage providers
    priority: 60
  
  observability:
    name: Observability
    icon: "📊"
    description: Monitoring and logging
    priority: 70
  
  gitops:
    name: GitOps
    icon: "🔄"
    description: GitOps tools
    priority: 80
  
  apps:
    name: Apps
    icon: "📦"
    description: Applications
    priority: 100
```

### Category Priority

Priority determines:
1. **Installation order** — Lower priority installs first
2. **Kustomization dependencies** — Each category depends on previous
3. **UI sort order** — Categories displayed in priority order

## JSON Schema Reference

### Simple Fields

```yaml
jsonSchema:
  type: object
  properties:
    replicaCount:
      type: integer
      title: Replicas
      minimum: 1
      default: 1
    
    enabled:
      type: boolean
      title: Enabled
      default: true
```

### Nested Objects

```yaml
jsonSchema:
  type: object
  properties:
    service:
      type: object
      title: Service
      properties:
        type:
          type: string
          enum: [ClusterIP, NodePort, LoadBalancer]
          default: ClusterIP
```

### Resources Pattern

```yaml
jsonSchema:
  type: object
  properties:
    resources:
      type: object
      properties:
        requests:
          type: object
          properties:
            cpu:
              type: string
              default: "100m"
            memory:
              type: string
              default: "128Mi"
```

## UI Schema Reference

```yaml
uiSchema:
  replicaCount:
    ui:widget: updown
  
  serviceType:
    ui:widget: select
  
  resources:
    ui:collapsed: true
  
  enabled:
    ui:help: "Enable this feature"
```

## Validation

```bash
# Validate single component
make validate-component COMPONENT=my-component

# Validate all components
make validate-all

# Check for version updates
make update-versions

# Show component architecture
python scripts/update-chart-versions.py --architecture
```

## Best Practices

1. **Keep defaults minimal** — Only essential values
2. **Use meaningful descriptions** — Help users understand options
3. **Add docs URL** — Link to official documentation
4. **Test with UI** — Verify form renders correctly
5. **Use correct category** — Place in appropriate category
6. **Set proper dependencies** — Ensure correct installation order

## Example: Adding External DNS

```bash
# Generate
./scripts/add-component.sh \
  --id external-dns \
  --repo https://kubernetes-sigs.github.io/external-dns/ \
  --chart external-dns \
  --version 1.14.3 \
  --category system \
  --docs-url https://github.com/kubernetes-sigs/external-dns

# Review
cat backend/definitions/components/external-dns.yaml

# Validate
make validate-component COMPONENT=external-dns

# Test in UI
make dev
```

## Example: Adding Operator + Instance

```bash
# 1. Add operator
./scripts/add-component.sh \
  --id my-operator \
  --repo https://... \
  --operator \
  --category observability

# 2. Add instance component
./scripts/add-component.sh \
  --id my-instance \
  --repo https://... \
  --multi-instance \
  --requires-operator my-operator \
  --category observability

# 3. Verify architecture
python scripts/update-chart-versions.py --architecture
```

## Example: Adding Dependent Configuration

For components that need another component but aren't multi-instance (like MetalLB + MetalLB Config):

```bash
# 1. Add main component
./scripts/add-component.sh \
  --id metallb \
  --repo https://metallb.github.io/metallb \
  --chart metallb \
  --category ingress

# 2. Add configuration component that depends on main
./scripts/add-component.sh \
  --id metallb-config \
  --repo https://... \
  --requires-operator metallb \
  --category ingress
```

Then edit the generated YAML to add `dependsOn`:

```yaml
# metallb-config.yaml
id: metallb-config
name: MetalLB Configuration
requiresOperator: metallb  # Blocks UI selection until metallb selected
dependsOn:
  - metallb                # Ensures installation after metallb
```
