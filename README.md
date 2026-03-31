# K8s Bootstrap

> Like [vim-bootstrap](https://vim-bootstrap.com), but for Kubernetes

Generate GitOps-ready bootstrap configurations for your Kubernetes clusters. Select components through a beautiful UI, configure them, and get a single command that sets up everything.

## ✨ Features

- 🎨 **Beautiful Web UI** — Select and configure Kubernetes components visually
- 🔄 **Pure GitOps** — Complete Flux CD setup, no manual helm installs
- 📦 **Vendored Charts** — All Helm charts stored in your repository
- 🚀 **One Command** — Single curl command bootstraps your entire cluster
- 🔧 **Extensible** — Add new components with simple YAML definitions
- 🔒 **Kubernetes-native** — Pure Helm + Flux approach

## 🚀 Quick Start

### 1. Start the Service

```bash
docker compose up -d
```

Open <http://localhost:3000>

### 2. Select Components

Choose from:

- **Ingress** — nginx, traefik
- **Security** — cert-manager, sealed-secrets, oauth2-proxy
- **Observability** — prometheus, grafana, loki
- **Storage** — longhorn, velero
- And more...

### 3. Configure & Generate

Fill in your Git repository URL and run the generated command:

```bash
bash -c "$(curl -fsSL https://your-instance/bootstrap/TOKEN)"
```

That's it! Flux will automatically deploy and manage all selected components.

### Or Use a Bundle

Bundles are curated stacks with a guided wizard. Instead of picking individual components, select a bundle and configure it step by step:

| Bundle | Description |
|--------|-------------|
| **KubeVirt Stack** | Complete virtualization platform — CNI, storage, ingress, KubeVirt |
| **Multi-Tenant Platform** | IaaS with Kamaji tenant isolation (hidden — development) |

Bundles handle component dependencies, exclusive groups (e.g., Longhorn *or* Linstor), and conditional parameters automatically. See [Bundles](docs/bundles.md) for details.

To show hidden/experimental bundles via the API:

```bash
curl http://localhost:8000/api/bundles?show_hidden=true
```

## 📖 Documentation

| Document | Description |
|----------|-------------|
| **[User Guide](docs/user-guide.md)** | How to use the service |
| **[Architecture](docs/architecture.md)** | How it works, chart structure, Flux resources |
| **[Developer Guide](docs/developer-guide.md)** | Code structure and contribution |
| **[Development Environment](docs/development-environment.md)** | Local dev setup with Docker |
| **[Testing](docs/testing.md)** | Running and writing tests |
| **[Adding Components](docs/adding-components.md)** | Create new component definitions |
| **[Bundles](docs/bundles.md)** | Curated component stacks (KubeVirt, Multi-Tenant) |
| **[Production Deployment](docs/production-deployment.md)** | Deploy to production with Docker and TLS |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Frontend (Next.js)                   │    │
│  │                    http://localhost:3000                │    │
│  │  • Component selection UI                               │    │
│  │  • Configuration forms                                  │    │
│  │  • Proxies /api/* and /bootstrap/* to backend           │    │
│  └────────────────────────────┬────────────────────────────┘    │
│                               │ internal                        │
│                               ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Backend (FastAPI)                    │    │
│  │                    (not exposed externally)             │    │
│  │  • Component definitions                                │    │
│  │  • Repository generation                                │    │
│  │  • Bootstrap script creation                            │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼ curl command
┌─────────────────────────────────────────────────────────────────┐
│                      User's Machine                             │
│  bash -c "$(curl -fsSL .../bootstrap/TOKEN)"                    │
│                               │                                 │
│                               ▼                                 │
│  • Creates directory with all files                             │
│  • Downloads Helm charts via `helm pull`                        │
│  • Initializes Git repo, pushes to remote                       │
│  • Installs Flux Operator                                       │
│  • Flux syncs everything automatically                          │
└─────────────────────────────────────────────────────────────────┘
```

## 📦 Generated Repository Structure

```
my-cluster/
├── bootstrap.sh                       # Main installation script
├── k8s-bootstrap.yaml                 # Config for re-import/updates
├── README.md                          # Generated documentation
│
├── charts/                            # Helm charts by category
│   ├── core/
│   │   ├── flux-operator/             # Flux Operator (vendored)
│   │   ├── flux-instance/             # GitRepository + Kustomizations
│   │   └── namespaces/                # Namespace management
│   ├── system/
│   │   └── metrics-server/            # Wrapper + vendored chart
│   ├── security/
│   │   └── cert-manager/
│   └── observability/
│       └── grafana-operator/
│
├── manifests/
│   ├── kustomizations/                # Flux Kustomization resources
│   │   ├── 00-namespaces.yaml
│   │   ├── 10-releases-core.yaml
│   │   ├── 20-releases-crds.yaml
│   │   └── ...                        # One per category
│   ├── namespaces/
│   │   └── release.yaml               # HelmRelease for namespaces
│   └── releases/                      # HelmReleases by category
│       ├── core/
│       │   ├── flux-operator.yaml
│       │   └── flux-instance.yaml
│       ├── security/
│       │   └── cert-manager.yaml
│       └── observability/
│           └── grafana-operator.yaml
│
└── vendor-charts.sh                   # Re-download vendored charts
```

## 🔧 Development

```bash
# Start development environment (includes local k8s cluster)
make dev

# Open toolbox shell with kubectl, helm, git
make dev-shell

# Run all tests
make test-all
```

See [Development Environment](docs/development-environment.md) for full setup guide.

## 🧪 Testing

```bash
# Unit tests (fast, no cluster needed)
make test-unit

# Integration tests (needs backend)
make test-integration

# E2E tests (creates kind cluster)
make test-e2e

# All tests
make test-all
```

See [Testing Guide](docs/testing.md) for details.

## 📦 Chart Maintenance

Keep component charts up to date:

```bash
# Check for newer chart versions
make update-versions

# Update versions + auto-fix validation errors
make update-versions-apply

# Validate all component configurations
docker run --rm -v $(pwd)/backend/definitions:/app/backend/definitions \
  chart-updater --validate
```

The update tool:

- Queries upstream registries for latest versions
- Validates `defaultValues` against chart schemas
- Auto-fixes validation errors (removes invalid, adds required properties)

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Add/modify component definitions in `backend/definitions/components/`
4. Test with `make test-all`
5. Submit a pull request

## 📄 License

AGPL-3.0 - see [LICENSE](LICENSE)

---

Built with ❤️ for the Kubernetes community
