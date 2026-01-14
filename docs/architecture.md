# Architecture

This document explains how k8s-bootstrap generates repositories, the structure of generated content, and key architectural decisions.

## Table of Contents

- [Generation Flow](#generation-flow)
- [Generated Repository Structure](#generated-repository-structure)
- [Category-Based Organization](#category-based-organization)
- [Flux Architecture](#flux-architecture)
- [Chart Generation](#chart-generation)
- [Multi-Instance Components](#multi-instance-components)
- [Namespace Management](#namespace-management)
- [Dependency Resolution](#dependency-resolution)

## Generation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. User selects components in UI                               │
│     └── cert-manager, ingress-nginx, grafana-operator...        │
├─────────────────────────────────────────────────────────────────┤
│  2. Backend resolves dependencies                               │
│     ├── Auto-includes CRD charts (cert-manager-crds)            │
│     ├── Auto-includes sub-components (istio → istio-base, etc.) │
│     ├── Validates operator requirements                         │
│     └── Calculates installation order by category priority      │
├─────────────────────────────────────────────────────────────────┤
│  3. Backend generates repository structure                      │
│     ├── Charts organized by category (core/, system/, ingress/) │
│     ├── HelmRelease manifests in manifests/releases/<category>/ │
│     ├── Kustomizations in manifests/kustomizations/             │
│     └── Namespaces chart with all required namespaces           │
├─────────────────────────────────────────────────────────────────┤
│  4. User runs curl command                                      │
│     ├── Script creates all directories and files                │
│     ├── vendor-charts.sh downloads upstream charts              │
│     ├── Git init, commit, push                                  │
│     └── Installation: flux-operator → FluxInstance → Flux       │
├─────────────────────────────────────────────────────────────────┤
│  5. Flux takes over                                             │
│     ├── GitRepository syncs from remote                         │
│     ├── Kustomizations apply HelmReleases by category priority  │
│     └── HelmReleases install components                         │
└─────────────────────────────────────────────────────────────────┘
```

## Generated Repository Structure

```
my-cluster/
├── k8s-bootstrap.yaml                # Component selections (import back to UI)
├── bootstrap.sh                      # Installation script
├── vendor-charts.sh                  # Script to download Helm dependencies
├── README.md                         # Usage instructions
├── .gitignore                        # Git ignore patterns
│
├── charts/
│   ├── core/                         # Core components (priority 10)
│   │   ├── flux-operator/            # Flux Operator wrapper chart
│   │   │   ├── Chart.yaml
│   │   │   ├── values.yaml
│   │   │   └── charts/flux-operator/ # Vendored upstream
│   │   ├── flux-instance/            # Flux Instance configuration
│   │   │   ├── Chart.yaml
│   │   │   ├── values.yaml
│   │   │   └── templates/
│   │   │       ├── gitrepository.yaml
│   │   │       └── secret-git-credentials.yaml
│   │   └── namespaces/               # Namespaces chart
│   │       ├── Chart.yaml
│   │       ├── values.yaml
│   │       └── templates/namespaces.yaml
│   │
│   ├── crds/                         # CRD components (priority 20)
│   │   └── cert-manager-crds/
│   │
│   ├── system/                       # System components (priority 30)
│   │   └── metrics-server/
│   │
│   ├── ingress/                      # Ingress components (priority 40)
│   │   └── ingress-nginx/
│   │
│   ├── security/                     # Security components (priority 50)
│   │   └── cert-manager/
│   │
│   └── observability/                # Observability components (priority 70)
│       ├── grafana-operator/
│       └── grafana-instance/
│
├── manifests/
│   ├── kustomizations/               # Flux Kustomizations (static files)
│   │   ├── 00-namespaces.yaml        # Applies manifests/namespaces/
│   │   ├── 10-releases-core.yaml     # Applies manifests/releases/core/
│   │   ├── 20-releases-crds.yaml     # Applies manifests/releases/crds/
│   │   ├── 30-releases-system.yaml   # ...and so on
│   │   ├── 40-releases-ingress.yaml
│   │   ├── 50-releases-security.yaml
│   │   └── 70-releases-observability.yaml
│   │
│   ├── namespaces/                   # Namespace HelmRelease
│   │   └── release.yaml
│   │
│   └── releases/                     # Component HelmReleases by category
│       ├── core/
│       │   ├── flux-operator.yaml
│       │   └── flux-instance.yaml
│       ├── crds/
│       │   └── cert-manager-crds.yaml
│       ├── system/
│       │   └── metrics-server.yaml
│       ├── ingress/
│       │   └── ingress-nginx.yaml
│       ├── security/
│       │   └── cert-manager.yaml
│       └── observability/
│           ├── grafana-operator.yaml
│           └── grafana-instance.yaml
│
└── .age/                             # Age encryption keys (private repos)
    └── key.txt                       # Private key (in .gitignore)
```

### k8s-bootstrap.yaml

This file stores your component selections and configuration:

```yaml
version: '1.0'
clusterName: my-cluster
repoUrl: git@github.com:org/k8s-gitops.git
branch: main
selections:
  - id: cert-manager
    enabled: true
    values:
      installCRDs: true
    rawOverrides: ''
  - id: grafana-operator
    enabled: true
  - id: grafana-instance
    enabled: true
    instances:
      - name: production
        namespace: monitoring
        values:
          ingress:
            enabled: true
            host: grafana.example.com
```

**Usage:** Import this file back into the K8s Bootstrap UI to:

- Restore your previous selections
- Add or modify components
- Re-generate with updated settings

## Category-Based Organization

Components are organized by categories with priorities that determine installation order:

| Priority | Category | Description |
|----------|----------|-------------|
| 10 | core | Flux components, namespaces |
| 20 | crds | CRD-only charts (installed before main components) |
| 30 | system | Core system components (DNS, autoscaler) |
| 40 | ingress | Ingress controllers, load balancers |
| 50 | security | Certificates, secrets, authentication |
| 60 | storage | Storage providers, backups |
| 70 | observability | Monitoring, logging, tracing |
| 80 | gitops | GitOps tools (ArgoCD, Weave) |
| 100 | apps | User applications |

### Why Categories?

1. **Installation Order** — Lower priority categories install first
2. **Organization** — Easy to find and manage related components
3. **Dependencies** — Categories automatically depend on lower-priority categories
4. **UI Grouping** — Components grouped logically in the UI

## Flux Architecture

### Kustomization Chain

Flux uses a chain of Kustomizations to apply resources in order:

```
namespaces (priority: 00)
    ↓ dependsOn
releases-core (priority: 10)
    ↓ dependsOn
releases-crds (priority: 20)
    ↓ dependsOn
releases-system (priority: 30)
    ↓ dependsOn
releases-ingress (priority: 40)
    ↓ dependsOn
...
```

Each Kustomization:

- Points to a directory in `manifests/releases/<category>/`
- Depends on the previous category's Kustomization
- Contains HelmRelease manifests for that category

### HelmRelease Structure

Each component has its own HelmRelease file:

```yaml
# manifests/releases/security/cert-manager.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: cert-manager
  namespace: cert-manager
spec:
  interval: 30m
  chart:
    spec:
      chart: ./charts/security/cert-manager
      sourceRef:
        kind: GitRepository
        name: flux-system
        namespace: flux-system
  install:
    createNamespace: false
  dependsOn:
    - name: cert-manager-crds
      namespace: flux-system
  values:
    cert-manager:
      replicaCount: 2
```

### Why Separate HelmRelease Files?

| Feature | Benefit |
|---------|---------|
| **Easy editing** | Change one component without touching others |
| **Git history** | Track changes per component |
| **Smaller files** | Easier to review and merge |
| **Independent updates** | Update workflow only modifies changed files |

## Chart Generation

### Wrapper Chart Pattern

Each component uses a "wrapper chart" that depends on the upstream chart:

```yaml
# charts/security/cert-manager/Chart.yaml
apiVersion: v2
name: cert-manager
version: 1.14.3
dependencies:
  - name: cert-manager
    version: "1.14.3"
    repository: "file://charts/cert-manager"
```

### Values Structure

User configuration is nested under the upstream chart name:

```yaml
# charts/security/cert-manager/values.yaml (defaults only)
cert-manager:
  installCRDs: false

# manifests/releases/security/cert-manager.yaml (actual values)
spec:
  values:
    cert-manager:
      installCRDs: true
      replicaCount: 2
```

## Multi-Instance Components

Some components can be deployed multiple times:

### Operators vs Instances

```
┌─────────────────────────────────────────────────────────────────┐
│  Grafana Operator (isOperator: true)                            │
│  └── Deployed once, manages multiple Grafana instances          │
├─────────────────────────────────────────────────────────────────┤
│  Grafana Instance (multiInstance: true)                         │
│  ├── Instance: "production" in namespace "monitoring"           │
│  │   └── grafana-instance-production.yaml                       │
│  ├── Instance: "staging" in namespace "staging-monitoring"      │
│  │   └── grafana-instance-staging.yaml                          │
│  └── Each instance has its own HelmRelease                      │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Instance Definition

```yaml
# Component definition
id: grafana-instance
multiInstance: true
requiresOperator: grafana-operator
defaultNamespace: monitoring
```

### Generated HelmReleases

For each instance, a separate HelmRelease is generated:

```yaml
# manifests/releases/observability/grafana-instance-production.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: grafana-instance-production
  namespace: monitoring
spec:
  values:
    grafana:
      ingress:
        enabled: true
        host: grafana.example.com
```

## Namespace Management

### Namespaces Chart

All namespaces are managed by a dedicated chart:

```yaml
# manifests/namespaces/release.yaml
spec:
  values:
    namespaces:
      - cert-manager
      - ingress-nginx
      - monitoring
      - staging-monitoring
```

### Why Centralized Namespaces?

1. **Single source of truth** — All namespaces in one place
2. **Proper ordering** — Namespaces created before HelmReleases
3. **No duplicates** — Kustomize won't complain about duplicate definitions
4. **Dynamic** — Namespaces added automatically for multi-instance components

## Dependency Resolution

### Component Definition

```yaml
# backend/definitions/components/cert-manager.yaml
id: cert-manager
dependsOn:
  - namespaces
  - cert-manager-crds

# Auto-include CRDs when this is selected
autoInclude:
  when: [cert-manager]
```

### Meta-Components

Some components are "meta" that auto-include others:

```yaml
# istio.yaml (meta-component)
id: istio
chartType: meta
autoIncludes:
  - istio-base
  - istiod
  - istio-gateway
```

When user selects "Istio", all sub-components are automatically included.

## Summary

| Concept | Purpose |
|---------|---------|
| **Category-based structure** | Organize charts and manifests by type |
| **Separate HelmRelease files** | Easy editing, clear git history |
| **Kustomization chain** | Ensures correct installation order |
| **Multi-instance support** | Deploy same component multiple times |
| **Meta-components** | Simplify complex component groups |
| **Namespaces chart** | Centralized namespace management |
