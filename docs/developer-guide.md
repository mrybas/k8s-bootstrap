# Developer Guide

This guide explains the architecture and how to contribute.

**Related Documentation:**
- [Architecture](architecture.md) — Generated structure, Flux resources
- [Development Environment](development-environment.md) — Local dev setup
- [Testing](testing.md) — Running and writing tests
- [Adding Components](adding-components.md) — Create component definitions

## Architecture Overview

```
k8s-bootstrap/
├── frontend/              # Next.js 14 (React)
│   ├── src/
│   │   ├── app/           # App router pages
│   │   ├── components/    # React components
│   │   └── types/         # TypeScript types
│   └── next.config.js     # Proxies /api/*, /bootstrap/*, /update/*
│
├── backend/               # FastAPI (Python)
│   ├── app/
│   │   ├── main.py        # API endpoints
│   │   ├── core/          # Config, definitions loader
│   │   └── generator/     # Repository generation
│   │       ├── repo_generator.py      # Main orchestrator
│   │       ├── chart_generator.py     # Wrapper charts
│   │       ├── bootstrap_generator.py # Flux charts, scripts
│   │       ├── update_generator.py    # Update scripts
│   │       └── template_engine.py     # Jinja2 rendering
│   ├── definitions/
│   │   ├── categories.yaml
│   │   └── components/
│   └── templates/         # Jinja2 templates
│
├── dev/                   # Development environment
│   ├── docker-compose.yml
│   └── Dockerfile.toolbox
│
├── tests/                 # Test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── scripts/               # Helper scripts
    ├── component_generator.py     # Add new components
    └── update-chart-versions.py   # Version management
```

## Key Concepts

### Category-Based Organization

Components are organized by categories with priorities:

```python
# Categories determine:
# 1. Chart location: charts/<category>/<component>/
# 2. HelmRelease location: manifests/releases/<category>/
# 3. Installation order: lower priority = earlier
# 4. Kustomization dependencies
```

### Multi-Instance Components

```python
# Definition
multiInstance: true
requiresOperator: grafana-operator

# Results in:
# - Multiple HelmReleases: grafana-instance-<name>.yaml
# - Each with its own namespace
# - UI for managing instances
```

### Meta-Components

```python
# Definition
chartType: meta
autoIncludes: [istio-base, istiod, istio-gateway]

# Results in:
# - No chart generated for meta-component
# - Sub-components auto-selected
# - Sub-components generate their own HelmReleases
```

## Development Setup

### Prerequisites

- Docker
- Docker Compose

### Start Environment

```bash
# Full environment
make dev

# Open toolbox shell
make dev-shell
```

### URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | - |
| Backend API | http://localhost:8000 | - |
| Gitea | http://localhost:3030 | dev / dev12345 |

## Code Structure

### Backend Generators

```
backend/app/generator/
├── repo_generator.py      # Orchestrates everything
│   ├── _generate_namespaces_chart()
│   ├── _generate_release_manifests()    # HelmReleases by category
│   ├── _generate_kustomization_manifests()
│   └── _generate_config_file()          # k8s-bootstrap.yaml
│
├── chart_generator.py     # Wrapper charts
│   └── generate()         # Chart.yaml, values.yaml
│
├── bootstrap_generator.py # Flux components
│   ├── generate_flux_operator()
│   ├── generate_flux_instance()
│   └── generate_bootstrap_script()
│
├── update_generator.py    # Update functionality
│   └── generate_update_script()
│
└── template_engine.py     # Jinja2 rendering
```

### Templates Structure

```
backend/app/templates/
├── charts/
│   ├── flux-operator/
│   ├── flux-instance/
│   │   ├── Chart.yaml.j2
│   │   ├── values.yaml.j2
│   │   └── templates/
│   │       ├── gitrepository.yaml.j2
│   │       └── secret-git-credentials.yaml.j2
│   ├── namespaces/
│   └── wrapper/              # Generic wrapper template
│
├── manifests/
│   ├── kustomizations/
│   │   ├── namespaces.yaml.j2
│   │   └── category.yaml.j2
│   ├── namespaces/
│   │   └── release.yaml.j2
│   └── releases/
│       └── helmrelease.yaml.j2
│
└── scripts/
    ├── bootstrap.sh.j2
    ├── update.sh.j2
    └── vendor-charts.sh.j2
```

### Frontend Components

```
frontend/src/components/
├── ComponentCard.tsx     # Component selection card
├── ConfigModal.tsx       # Component configuration
├── InstanceModal.tsx     # Multi-instance management
├── GenerateModal.tsx     # Bootstrap/update generation
├── Header.tsx
├── Hero.tsx
└── Footer.tsx
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/categories` | GET | List categories with components |
| `/api/bootstrap` | POST | Create bootstrap session |
| `/api/update` | POST | Create update session |
| `/bootstrap/{token}` | GET | Get bootstrap script |
| `/update/{token}` | GET | Get update script |

### Bootstrap Request

```json
{
  "cluster_name": "my-cluster",
  "repo_url": "https://github.com/org/repo.git",
  "branch": "main",
  "components": [
    {
      "id": "cert-manager",
      "enabled": true,
      "values": {"installCRDs": true},
      "rawOverrides": ""
    },
    {
      "id": "grafana-instance",
      "enabled": true,
      "instances": [
        {
          "name": "production",
          "namespace": "monitoring",
          "values": {"ingress": {"enabled": true}}
        }
      ]
    }
  ]
}
```

## Adding Features

### New Component Type

1. Update `backend/definitions/components/` schema
2. Update `backend/app/main.py` to pass new fields
3. Update `frontend/src/types/index.ts`
4. Update `frontend/src/components/ComponentCard.tsx`
5. Update generators if needed

### New Template

1. Create `.j2` file in `backend/app/templates/`
2. Update appropriate generator to render it
3. Add tests

## Scripts

### Component Generator

```bash
# Interactive
make add-component

# CLI
./scripts/add-component.sh --id my-comp --repo https://...

# Shows operator/instance architecture
python scripts/update-chart-versions.py --architecture
```

### Version Management

The `update-chart-versions.py` script manages Helm chart versions:

```bash
# Show current vs latest versions
python scripts/update-chart-versions.py

# Filter by component
python scripts/update-chart-versions.py --component grafana-operator

# Update versions in definition files
python scripts/update-chart-versions.py --update

# Update specific component only
python scripts/update-chart-versions.py --update --component cert-manager

# Validate defaultValues against chart schemas
python scripts/update-chart-versions.py --validate

# Auto-fix invalid values (remove disallowed properties)
python scripts/update-chart-versions.py --fix

# Show operator/instance architecture
python scripts/update-chart-versions.py --architecture

# Output as JSON
python scripts/update-chart-versions.py --json
```

**Make targets:**

```bash
make update-versions         # Check versions (dry-run)
make update-versions-apply   # Update + validate + fix
```

**What the script does:**

1. **Version checking** — Queries OCI registries and Helm repos for latest versions
2. **Schema validation** — Validates `defaultValues` against chart's `values.schema.json`
3. **Auto-fixing** — Removes disallowed properties, adds missing required ones
4. **Architecture view** — Shows operator/instance relationships

**Running in Docker:**

```bash
# From toolbox container
docker compose -f dev/docker-compose.yml exec toolbox \
  python /project/scripts/update-chart-versions.py --architecture

# Or via make
make dev-shell
python /project/scripts/update-chart-versions.py --update --component metallb
```

## Testing

```bash
make test-all         # All tests
make test-unit        # Unit tests
make test-integration # API tests
make test-e2e         # Full E2E
```

See [Testing](testing.md) for details.

## Common Tasks

### Debug Generated Script

```bash
curl http://localhost:8000/bootstrap/TOKEN > script.sh
less script.sh
```

### Rebuild Containers

```bash
cd dev
docker compose build --no-cache
docker compose up -d
```

### Check Component Architecture

```bash
docker compose -f dev/docker-compose.yml exec toolbox \
  python /project/scripts/update-chart-versions.py --architecture
```

## Code Style

- **Python**: Black formatter, type hints
- **TypeScript**: ESLint + Prettier

## Contributing

1. Fork repository
2. Create feature branch
3. Make changes
4. Run tests: `make test-all`
5. Submit PR
