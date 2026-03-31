# Bundles

Bundles are curated stacks of components that work together. Instead of selecting individual components, you pick a bundle and configure it through a guided wizard.

## Table of Contents

- [What Is a Bundle](#what-is-a-bundle)
- [Available Bundles](#available-bundles)
  - [Virtualization Platform](#virtualization-platform)
  - [Multi-Tenant Platform](#multi-tenant-platform)
- [Using Bundles](#using-bundles)
- [Bundle Parameters](#bundle-parameters)
- [Hidden Bundles](#hidden-bundles)
- [Creating a Custom Bundle](#creating-a-custom-bundle)
- [Bundle Definition Reference](#bundle-definition-reference)

## What Is a Bundle

A bundle is a YAML file in `backend/definitions/bundles/` that defines:

1. **Components** — which Helm charts to include, with dependency ordering
2. **Parameters** — user-configurable options presented as a wizard
3. **Exclusive groups** — mutually exclusive choices (e.g., Longhorn *or* Linstor)
4. **CNI/DNS bootstrap** — pre-Flux installation for clusters without networking
5. **Notes** — guidance shown to the user during configuration

Bundles differ from plain component selection in that they:
- Pre-select a tested combination of components
- Mark some components as required and others as optional
- Provide a parameter-driven wizard instead of per-component configuration
- Handle complex `show_if` conditions between parameters

## Available Bundles

### Virtualization Platform

| | |
|---|---|
| **ID** | `virtualization-platform` |
| **File** | `backend/definitions/bundles/virtualization-platform.yaml` |
| **Category** | Virtualization |
| **Hidden** | No |

Complete virtualization stack for running VMs on Kubernetes. Includes CNI, storage, ingress, and KubeVirt.

**Required components:**
- kube-ovn — Primary CNI with OVN (VPC isolation, IPAM, live migration)
- multus-cni — Multiple network interfaces for VMs
- coredns — Cluster DNS
- kubevirt-operator + CRDs — VM lifecycle management
- kubevirt-cdi + CRDs — Disk image import

**Optional components (enabled by default):**
- cilium — eBPF network policies and Hubble observability
- longhorn — Distributed block storage (default storage backend)
- metallb + config — Bare-metal load balancer
- ingress-nginx — NGINX ingress controller (default)
- snapshot-controller — Volume snapshots for VMs

**Optional components (disabled by default):**
- piraeus/linstor — High-performance DRBD storage (alternative to Longhorn)
- ingress-traefik — Traefik ingress (alternative to NGINX)
- velero — Backup and disaster recovery
- victoria-metrics stack — Monitoring (Victoria Metrics + Grafana)

**Parameter categories:**
1. Environment — bare-metal vs cloud
2. Networking — CNI mode, bootstrap CNI toggle
3. Ingress & Domains — controller choice, IP, base domain
4. Storage — Longhorn vs Linstor, replicas, pool config
5. Backup — Velero toggle
6. Observability — Hubble, monitoring, Grafana

### Multi-Tenant Platform

| | |
|---|---|
| **ID** | `multi-tenant-stack` |
| **File** | `backend/definitions/bundles/multi-tenant-stack.yaml` |
| **Category** | Multi-tenancy |
| **Hidden** | Yes (development/experimental) |

IaaS platform extending the Virtualization Platform with tenant isolation via [Kamaji](https://github.com/clastix/kamaji). Each tenant gets a virtual Kubernetes cluster (API server as a Pod) with shared or dedicated worker nodes.

**Additional required components (beyond Virtualization Platform):**
- cert-manager — TLS certificates (required by Kamaji webhooks)
- cloudnative-pg — PostgreSQL operator for Kamaji DataStore
- cnpg-cluster — PostgreSQL cluster instance
- kamaji + CRDs — Tenant control plane manager
- kamaji-datastore — PostgreSQL DataStore for kine backend
- capi-operator — Cluster API Operator
- capi-providers — CAPI providers (Core, Bootstrap, Kamaji CP, KubeVirt Infra)

**Additional optional components:**
- minio — S3-compatible storage for backups and artifacts

**Additional parameter categories:**
- Multi-tenancy — DataStore backend (PostgreSQL/etcd), Cluster API toggle

## Using Bundles

### In the UI

1. Open the K8s Bootstrap frontend
2. Select a bundle from the bundle list
3. Walk through the parameter wizard — each category is a step
4. Review the component list (required components are locked, optional ones can be toggled)
5. Generate and run the bootstrap command

### Via API

```bash
# List visible bundles
curl http://localhost:8000/api/bundles

# List all bundles (including hidden)
curl http://localhost:8000/api/bundles?show_hidden=true

# Get a specific bundle
curl http://localhost:8000/api/bundles/virtualization-platform
```

## Bundle Parameters

Parameters drive the wizard UI. Each parameter has:

| Field | Description |
|-------|-------------|
| `id` | Unique identifier |
| `name` | Display name |
| `description` | Help text shown to the user |
| `type` | `select`, `boolean`, or `string` |
| `options` | Choices for `select` type |
| `default` | Default value |
| `required` | Whether the field is mandatory |
| `category` | Groups parameters into wizard steps |
| `show_if` | Conditional visibility expression |
| `placeholder` | Placeholder text for `string` type |

### Conditional Visibility (`show_if`)

Parameters can depend on other parameters:

```yaml
- id: ingress_ip
  show_if: environment == "bare-metal" && ingress_controller != "none"
```

This field is only shown when the environment is bare-metal and an ingress controller is selected.

### Exclusive Groups

Components in the same `exclusive_group` are mutually exclusive:

```yaml
- id: longhorn
  exclusive_group: storage

- id: piraeus-operator
  exclusive_group: storage
```

Only one storage backend can be active at a time. The parameter `storage_backend` controls which one.

## Hidden Bundles

Bundles with `hidden: true` are excluded from the default API response. They are typically experimental or under development.

To see hidden bundles:

- **API:** `GET /api/bundles?show_hidden=true`
- **Frontend:** Hidden bundles are not shown in the standard UI (this is by design for production)

Currently hidden bundles:
- `multi-tenant-stack` — Multi-tenant platform (experimental)

## Creating a Custom Bundle

### 1. Create the definition file

```bash
# backend/definitions/bundles/my-stack.yaml
```

### 2. Define metadata

```yaml
id: my-stack
name: My Custom Stack
description: Short description of what this stack provides
icon: "🚀"
category: custom
# hidden: true  # uncomment to hide from default listing
```

### 3. Add components

```yaml
components:
  - id: cert-manager
    required: true
    description: TLS certificate management

  - id: ingress-nginx
    required: false
    default_enabled: true
    description: NGINX ingress controller
    exclusive_group: ingress

  - id: ingress-traefik
    required: false
    default_enabled: false
    description: Traefik ingress controller
    exclusive_group: ingress
```

Component fields:

| Field | Description |
|-------|-------------|
| `id` | Must match a component in `backend/definitions/components/` |
| `required` | Cannot be deselected by the user |
| `default_enabled` | Initial toggle state for optional components |
| `hidden` | Hidden from bundle UI (still installed if enabled) |
| `description` | Override description for this bundle context |
| `exclusive_group` | Mutual exclusion group name |
| `depends_on_bundle` | Another component in this bundle that must be installed first |

### 4. Add parameters

```yaml
parameters:
  - id: ingress_controller
    name: Ingress Controller
    type: select
    options:
      - value: nginx
        label: NGINX
      - value: traefik
        label: Traefik
      - value: none
        label: None
    default: nginx
    required: true
    category: ingress

parameter_categories:
  - id: ingress
    name: Ingress
    order: 1
```

### 5. Add optional sections

```yaml
# Pre-Flux CNI installation
cni_bootstrap:
  enabled: true
  component: kube-ovn

# Pre-Flux DNS installation
dns_bootstrap:
  enabled: true
  component: coredns

# User-facing notes
notes:
  - title: Prerequisites
    content: |
      Ensure your cluster has at least 3 nodes.

# Installation order
install_order:
  - cert-manager
  - ingress-nginx
  - ingress-traefik
```

### 6. Reload definitions

After saving the file, reload without restarting:

```bash
curl -X POST http://localhost:8000/api/reload-definitions
```

## Bundle Definition Reference

Full schema of a bundle YAML file:

```yaml
# Required
id: string              # Unique bundle identifier (filename without .yaml)
name: string            # Display name
description: string     # Short description

# Optional metadata
icon: string            # Emoji icon (default: "📦")
category: string        # Grouping category (default: "general")
hidden: boolean         # Hide from default listing (default: false)

# Component list
components:
  - id: string                  # Component ID (must exist in definitions/components/)
    required: boolean           # Cannot be deselected
    default_enabled: boolean    # Initial state for optional components
    hidden: boolean             # Hidden from UI
    description: string         # Context-specific description
    exclusive_group: string     # Mutual exclusion group
    depends_on_bundle: string   # Intra-bundle dependency

# Pre-Flux bootstrap
cni_bootstrap:
  enabled: boolean
  component: string             # Component ID to install before Flux
  description: string

dns_bootstrap:
  enabled: boolean
  component: string

# User configuration
parameters:
  - id: string
    name: string
    description: string
    type: select | boolean | string
    options: list               # For select type
    default: any
    required: boolean
    category: string            # Maps to parameter_categories
    show_if: string             # Conditional expression
    placeholder: string         # For string type

parameter_categories:
  - id: string
    name: string
    description: string
    order: integer              # Display order in wizard

# User-facing notes
notes:
  - title: string
    content: string             # Markdown content

# Installation order (list of component IDs)
install_order:
  - string
```
