# Developer Environment - Quick Reference

Full documentation: **[docs/development-environment.md](../docs/development-environment.md)**

## Quick Start

```bash
# From project root:
make dev          # Start all services
make dev-shell    # Open toolbox with k8s cluster
make dev-stop     # Stop services
make dev-clean    # Remove everything
```

## Services

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:3000 | Hot reload enabled |
| Backend | http://localhost:8000 | Hot reload enabled |
| Gitea | http://localhost:3030 | Login: dev / dev12345 |

## ⚠️ Bootstrap URLs

The dev environment is designed to test **from inside the toolbox container**.

When you generate a bootstrap command, you'll see **two URLs**:

| Context | URL | Use for |
|---------|-----|---------|
| Browser/Host | `localhost:3000` | Running from your machine |
| **Toolbox** | `frontend:3000` | Running from `make dev-shell` |

The toolbox container cannot access `localhost` — use the **Toolbox Command** shown in the modal.

## Workflow

1. `make dev` — Start environment
2. Open http://localhost:3000 — Configure in UI
3. Generate bootstrap package
4. `make dev-shell` — Open toolbox
5. Run **Toolbox Command** (with `frontend:3000`)
6. `kubectl get pods -A` — Verify

## Troubleshooting

```bash
# Logs
./dev/dev.sh logs

# Status
make dev-status

# Reset
make dev-clean && make dev
```
