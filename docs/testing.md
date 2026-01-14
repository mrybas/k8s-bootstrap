# Testing Guide

Complete guide to testing k8s-bootstrap. All tests run inside Docker containers.

## Quick Start

```bash
# Run all tests
make test-all

# Or run specific test types
make test-unit         # Fast, no cluster (~seconds)
make test-integration  # Needs backend (~minutes)
make test-e2e          # Creates kind cluster (~5-10 minutes)

# Debug mode - keeps cluster for inspection
make test-e2e-debug
```

## Test Architecture

### Test Levels

```
┌─────────────────────────────────────────────────────────────────┐
│  Level 1: Unit Tests                                            │
│  ├── No external dependencies                                   │
│  ├── Fast execution (~seconds)                                  │
│  ├── Tests: YAML validation, schema checks, dependencies        │
│  └── Location: tests/unit/                                      │
├─────────────────────────────────────────────────────────────────┤
│  Level 2: Integration Tests                                     │
│  ├── Requires: Backend API running                              │
│  ├── Medium execution (~1-2 minutes)                            │
│  ├── Tests: API endpoints, chart generation, helm lint          │
│  └── Location: tests/integration/                               │
├─────────────────────────────────────────────────────────────────┤
│  Level 3: E2E Tests                                             │
│  ├── Requires: Docker, kind cluster, Git server (Gitea)         │
│  ├── Execution time: ~5-10 minutes per scenario                 │
│  ├── Tests: Full GitOps bootstrap flow                          │
│  └── Location: tests/e2e/                                       │
└─────────────────────────────────────────────────────────────────┘
```

## Unit Tests

### What They Test

| Test File | Purpose |
|-----------|---------|
| `tests/unit/test_definitions.py` | Component definition validation |
| `tests/unit/test_component_generator.py` | Generator script validation |

### `test_definitions.py`

Tests all `backend/definitions/components/*.yaml`:

**TestDefinitionSyntax:**
- Valid YAML syntax
- Matches JSON schema
- ID matches filename

**TestDefinitionRequirements:**
- Visible components have docsUrl
- Upstream charts have upstream config
- Components have namespace
- Instances reference valid operators

**TestDefinitionReferences:**
- Dependencies exist
- RequiresCrds references exist
- No circular dependencies

**TestNamespaceStrategy:**
- CRD charts use `cluster-crds` namespace
- Flux components use `flux-system`
- Regular components have own namespaces

### Run Unit Tests

```bash
make test-unit

# Run specific test
make test-file FILE=tests/unit/test_definitions.py
```

## Integration Tests

### What They Test

| Test File | Purpose |
|-----------|---------|
| `tests/integration/test_chart_generation.py` | Chart generation and linting |

### `test_chart_generation.py`

**TestChartLinting:**
- Generated charts pass `helm lint`
- Flux charts are valid
- Namespaces chart is valid

**TestChartStructure:**
- Category-based chart paths (`charts/<category>/<component>/`)
- Wrapper chart dependencies
- Flux-instance templates (GitRepository only)

**TestManifestsStructure:**
- Kustomizations in `manifests/kustomizations/`
- HelmReleases in `manifests/releases/<category>/`
- Namespaces in `manifests/namespaces/`

**TestValuesGeneration:**
- Default values applied
- Custom values in HelmRelease (not chart values.yaml)
- Raw YAML overrides merged

**TestBootstrapScript:**
- Script exists and is executable
- Has 3-phase installation flow
- Supports kubeconfig flag

**TestAuthConfiguration:**
- Public repos don't generate auth secrets
- Private repos have auth templates

### Run Integration Tests

```bash
make test-integration
```

## E2E Tests

### What They Test

| Test File | Purpose |
|-----------|---------|
| `tests/e2e/test_bootstrap.py` | Structure validation |
| `tests/e2e/test_full_e2e.py` | Full GitOps flow |

### `test_full_e2e.py`

**TestPublicGiteaRepo:**
- Deploy from public Gitea repository
- Verify Flux reconciles components

**TestPrivateGiteaRepo:**
- Deploy with token authentication
- Verify Git credentials work

**TestUpdateWorkflow:**
- Initial bootstrap with basic components
- Add new component via update
- Verify Flux reconciles updates

### Run E2E Tests

```bash
# Basic E2E
make test-e2e

# Full E2E with repos
make test-e2e-full

# Debug mode
make test-e2e-debug
```

## GitLab Tests (Optional)

GitLab tests require a running GitLab instance:

```bash
# Start GitLab (~5 minutes)
make test-gitlab-start

# Run GitLab tests
make test-gitlab

# Stop GitLab
make test-gitlab-stop
```

## Available Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `kind_cluster` | session | Creates/manages kind cluster |
| `api_client` | session | requests.Session for API |
| `backend_url` | session | Backend URL string |
| `generate_bootstrap` | function | Factory to generate packages |
| `helm_lint` | function | Factory to lint charts |
| `helm_template` | function | Factory to template charts |

## Make Commands

| Command | Description |
|---------|-------------|
| `make test-unit` | Unit tests only |
| `make test-integration` | Integration tests |
| `make test-e2e` | E2E validation tests |
| `make test-all` | All tests in sequence |
| `make test-e2e-debug` | E2E, keep cluster |
| `make test-file FILE=...` | Run specific file |
| `make test-pattern PATTERN=...` | Run tests matching pattern |
| `make test-coverage` | With coverage report |
| `make test-clean` | Clean up resources |

## Writing Tests

### Unit Test Example

```python
class TestMyFeature:
    def test_something(self):
        assert True
```

### Integration Test Example

```python
def test_chart_generation(generate_bootstrap, helm_lint):
    bootstrap_dir = generate_bootstrap(
        components=["cert-manager"],
        cluster_name="test"
    )
    result = helm_lint(bootstrap_dir / "charts" / "security" / "cert-manager")
    assert result.returncode == 0
```

### E2E Test Example

```python
@pytest.mark.e2e
def test_deployment(kind_cluster, generate_bootstrap):
    bootstrap_dir = generate_bootstrap(
        components=["metrics-server"],
        cluster_name="e2e-test"
    )
    # Run bootstrap and verify
```

## Troubleshooting

### Kind Cluster Issues

```bash
kind get clusters
kind delete cluster --name k8s-bootstrap-test-*
```

### Tests Timeout

```bash
# Increase timeout
pytest tests/e2e -v --timeout=1200
```

### Debug Mode

```bash
make test-e2e-debug

# Inside shell:
kubectl get pods -A
flux get all -A
```
