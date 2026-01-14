# User Guide

K8s Bootstrap helps you create a GitOps-ready Kubernetes configuration in minutes.

## Overview

K8s Bootstrap generates:
1. A Git repository with all your selected Kubernetes components
2. Flux CD configuration for GitOps management
3. A single command to bootstrap everything

After running the bootstrap command, Flux automatically:
- Installs all selected components via HelmRelease
- Keeps them in sync with your Git repository
- Handles updates when you push changes

## Prerequisites

Your machine needs:
- `kubectl` — configured to access your cluster
- `helm` — for chart management
- `git` — for repository operations
- Access to a Git server (GitHub, GitLab, Gitea, etc.)

**For private repositories** (when Git authentication is enabled):
- `sops` — for encrypting credentials ([install guide](https://github.com/getsops/sops#download))
- `age` — for key management ([install guide](https://github.com/FiloSottile/age#installation))

Your Kubernetes cluster needs:
- At least 4GB RAM available
- Network access to your Git server
- Network access to Helm chart repositories

## Step-by-Step Guide

### Step 1: Select Components

Browse available components by category:

| Category | Examples |
|----------|----------|
| **Core** | flux-operator, namespaces |
| **System** | metrics-server, cluster-autoscaler |
| **Ingress** | ingress-nginx, istio |
| **Security** | cert-manager, sealed-secrets |
| **Observability** | grafana-operator, prometheus |
| **Storage** | longhorn, rook-ceph |

Click on components to select them. Dependencies are automatically resolved:
- Selecting `cert-manager` auto-includes `cert-manager-crds`
- Selecting `istio` auto-includes `istio-base`, `istiod`, `istio-gateway`

### Step 2: Configure Components

Click the ⚙️ icon on any component to customize it:
- Replica counts
- Resource limits
- Feature toggles

### Step 3: Configure Multi-Instance Components

For operator-based components (Grafana, Victoria Metrics, Rook Ceph):

1. **Select the operator** (e.g., `grafana-operator`)
2. **Add instances** via the instance component
3. **Configure each instance** with:
   - Instance name
   - Namespace
   - Ingress settings
   - Storage settings
   - Resources

### Step 4: Generate

Click **Generate** and fill in:

| Field | Description | Example |
|-------|-------------|---------|
| **Cluster Name** | Identifier | `production` |
| **Repository URL** | Git repo | `git@github.com:org/k8s.git` |
| **Branch** | Git branch | `main` |

### Step 5: Run the Command

Copy and run the generated curl command:

```bash
bash -c "$(curl -fsSL https://your-instance/bootstrap/TOKEN)"
```

The script will:
1. Create directory with all files
2. Download Helm charts
3. Initialize Git and push
4. Install Flux Operator
5. Apply Flux configuration

### Step 6: Monitor Progress

```bash
# Watch Flux resources
kubectl get kustomizations,helmreleases -A

# Use Flux CLI
flux get helmreleases -A
flux get kustomizations -A
```

## Updating Your Installation

### Using the UI (Recommended)

1. **Import existing config**: Click "Load Previous Config" and select `k8s-bootstrap.yaml` from your repo
2. **Make changes**: Add/remove components, modify settings
3. **Generate update**: Click Generate to get update command
4. **Run update**: The script will only modify changed files

### Manual GitOps Changes

Edit files directly in your repository:

```bash
cd my-cluster

# Edit HelmRelease values
vim manifests/releases/security/cert-manager.yaml

# Commit and push
git add -A && git commit -m "Update cert-manager" && git push
```

Flux will reconcile within minutes.

## Managing Multi-Instance Components

### Adding New Instances

1. Import your `k8s-bootstrap.yaml`
2. Click on the multi-instance component (e.g., Grafana Instance)
3. Click "Add Instance"
4. Configure: name, namespace, ingress, storage
5. Generate and run update

### Each Instance Gets

- Separate HelmRelease file
- Own namespace (optional)
- Individual configuration
- Independent lifecycle

## Generated Repository Structure

```
my-cluster/
├── k8s-bootstrap.yaml           # Your config (import to UI)
├── bootstrap.sh                 # Bootstrap script
├── vendor-charts.sh             # Chart download script
│
├── charts/
│   ├── core/                    # Core components
│   │   ├── flux-operator/
│   │   ├── flux-instance/
│   │   └── namespaces/
│   ├── security/                # Security components
│   │   └── cert-manager/
│   └── observability/           # Observability
│       ├── grafana-operator/
│       └── grafana-instance/
│
└── manifests/
    ├── kustomizations/          # Flux Kustomizations
    │   ├── 00-namespaces.yaml
    │   ├── 10-releases-core.yaml
    │   └── ...
    ├── namespaces/              # Namespace HelmRelease
    │   └── release.yaml
    └── releases/                # Component HelmReleases
        ├── core/
        ├── security/
        └── observability/
```

## Troubleshooting

### Check Flux Status

```bash
flux get all -A
kubectl describe helmrelease <name> -n <namespace>
flux logs
```

### Common Issues

**"HelmRelease not ready"**
```bash
kubectl describe helmrelease <name> -n <namespace>
# Check: chart download, values validation, dependencies
```

**"Kustomization path not found"**
```bash
# Ensure git push completed
git status
# Force Flux reconciliation
flux reconcile source git flux-system -n flux-system
```

**"Namespace not found"**
```bash
# Check namespaces Kustomization
kubectl get kustomization namespaces -n flux-system
# Verify namespace in release.yaml
cat manifests/namespaces/release.yaml
```

### Force Reconciliation

```bash
flux reconcile kustomization releases-security -n flux-system
flux reconcile helmrelease cert-manager -n cert-manager
```

## Security

### Git Authentication

**HTTPS with Token:**
- Token requested interactively during bootstrap
- Encrypted with SOPS + age before storing
- Stored as Kubernetes Secret in cluster
- Never committed to Git in plain text

**SSH:**
- Keys generated during bootstrap
- Add public key to Git server

### Credential Encryption (SOPS + age)

When Git authentication is enabled, K8s Bootstrap uses [SOPS](https://github.com/getsops/sops) with [age](https://github.com/FiloSottile/age) for secure credential handling:

1. **age key generation** — A new age keypair is created in `.age/key.txt` (gitignored)
2. **SOPS encryption** — Git credentials are encrypted before storing
3. **Kubernetes Secret** — Encrypted credentials are deployed to cluster

**Required tools:**
```bash
# macOS
brew install sops age

# Linux (Debian/Ubuntu)
sudo apt install age
# sops: download from https://github.com/getsops/sops/releases

# Verify installation
sops --version
age --version
```

### Secrets Best Practices

- Use tokens with minimal permissions (repo read/write only)
- Rotate tokens regularly
- Keep `.age/key.txt` secure (it's your decryption key)
- Consider `external-secrets` for enterprise

## Related Documentation

- [Architecture](architecture.md) — Technical details
- [Developer Guide](developer-guide.md) — Contributing
- [Adding Components](adding-components.md) — New components
