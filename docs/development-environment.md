# Development Environment

All-in-Docker development setup for k8s-bootstrap. **Only Docker is required** - all tools run in containers.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Components](#components)
- [Usage](#usage)
- [Development Workflow](#development-workflow)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Quick Start

```bash
# Start everything
make dev

# Open toolbox with k8s cluster + all tools
make dev-shell

# Stop
make dev-stop

# Clean everything
make dev-clean
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Host Machine (Docker only)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Docker Network                           │  │
│  │                                                           │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐   │  │
│  │  │Frontend │  │ Backend │  │  Gitea  │  │  Toolbox  │   │  │
│  │  │ :3000   │  │ :8000   │  │ :3030   │  │  (shell)  │   │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────┬─────┘   │  │
│  │       │            │            │             │          │  │
│  │       └────────────┴────────────┴─────────────┤          │  │
│  │                                               │          │  │
│  │                                    ┌──────────▼────────┐ │  │
│  │                                    │   Kind Cluster    │ │  │
│  │                                    │  (k8s in Docker)  │ │  │
│  │                                    │                   │ │  │
│  │                                    │  kubectl, helm,   │ │  │
│  │                                    │  git, flux CLI    │ │  │
│  │                                    └───────────────────┘ │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  📁 dev/workspace/      ← Generated files (gitignored)          │
│     ├── .kube/config    ← Kubeconfig                            │
│     └── repos/          ← Test repositories                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Frontend (Next.js)

- **Port:** 3000
- **Hot reload:** Enabled
- **Role:** User interface, proxies API calls to backend

### Backend (FastAPI)

- **Port:** 8000
- **Hot reload:** Enabled (source mounted)
- **Role:** API, generates bootstrap packages

### Gitea (Git Server)

- **Port:** 3030
- **Credentials:** dev / dev12345
- **Role:** Local Git server for testing

### Toolbox

- **Interactive shell** with all tools pre-installed:
  - kubectl
  - helm
  - git
  - flux CLI
  - kind
  - sops (secret encryption)
  - age (encryption keys)
- Creates Kind cluster automatically
- Access via `make dev-shell`

## Usage

### Start Environment

```bash
make dev
```

This starts:
- Frontend on http://localhost:3000
- Backend on http://localhost:8000
- Gitea on http://localhost:3030

### Open Toolbox

```bash
make dev-shell
```

Opens shell with:
- Pre-configured kubectl (Kind cluster)
- Helm installed
- Git configured
- Flux CLI available

### View Status

```bash
make dev-status
```

### View Logs

```bash
# All services
./dev/dev.sh logs

# Specific service
./dev/dev.sh logs backend
./dev/dev.sh logs frontend
```

### Stop Environment

```bash
make dev-stop    # Keep data
make dev-clean   # Remove everything
```

## Development Workflow

### 1. Start Environment

```bash
make dev
```

### 2. Open UI

Navigate to http://localhost:3000

- Select components
- Configure settings
- Use repository URL: `http://gitea:3000/dev/bootstrap-test.git`

### 3. Open Toolbox

```bash
make dev-shell
```

### 4. Run Bootstrap

In toolbox shell:
```bash
bash -c "$(curl -fsSL http://backend:8000/bootstrap/YOUR_TOKEN)"
```

### 5. Monitor

```bash
# Watch Flux resources
kubectl get kustomizations,helmreleases -A -w

# Check pods
kubectl get pods -A

# Flux CLI
flux get all -A
flux logs
```

## Configuration

### Service URLs

| Service | Host URL | Container URL |
|---------|----------|---------------|
| Frontend | http://localhost:3000 | http://frontend:3000 |
| Backend | http://localhost:8000 | http://backend:8000 |
| Gitea | http://localhost:3030 | http://gitea:3000 |

**Important:** Use container URLs when configuring in the UI (e.g., `http://gitea:3000/dev/repo.git`)

### Workspace

Generated files are stored in `dev/workspace/` (gitignored):

```
dev/workspace/
├── .kube/
│   └── config        # Kubeconfig
└── repos/
    └── bootstrap-test/  # Generated repositories
```

### Access Cluster from Host

```bash
export KUBECONFIG=$(pwd)/dev/workspace/.kube/config
kubectl get nodes
```

## Troubleshooting

### Services Not Starting

```bash
# Check logs
./dev/dev.sh logs

# Rebuild
cd dev && docker compose build --no-cache
```

### Port Conflicts

```bash
# Check what's using the port
lsof -i :3000

# Or change port in dev/docker-compose.yml
ports:
  - "3002:3000"
```

### Cluster Issues

In toolbox shell:
```bash
# Delete and recreate
kind delete cluster --name k8s-bootstrap-dev
exit
make dev-shell
```

### Reset Everything

```bash
make dev-clean
make dev
```

## File Structure

```
dev/
├── docker-compose.yml     # All services
├── Dockerfile.toolbox     # Toolbox image
├── toolbox-entrypoint.sh  # Cluster setup script
├── dev.sh                 # Management script
├── config.yaml            # Configuration
├── README.md              # Quick reference
└── workspace/             # Generated files (gitignored)
```

## Tips

### Hot Reload

Both frontend and backend have hot reload:
- **Frontend:** Edit `frontend/src/` — changes reflect immediately
- **Backend:** Edit `backend/app/` — uvicorn restarts

### Multiple Clusters

```bash
# In toolbox
CLUSTER_NAME=test-2 kind create cluster --name test-2
```

### Direct Docker Access

```bash
docker compose -f dev/docker-compose.yml exec toolbox kubectl get nodes
docker compose -f dev/docker-compose.yml exec toolbox helm list -A
```
