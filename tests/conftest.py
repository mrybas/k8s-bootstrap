"""
Pytest configuration and fixtures for k8s-bootstrap tests.

This module provides:
- Kind cluster management fixtures
- kubectl/helm wrapper functions
- Bootstrap package generation helpers
- Test utilities

Architecture Note:
- flux-operator: Installs Flux via FluxInstance CRD
- flux-instance: Contains GitRepository, Kustomizations, and all component HelmReleases
- namespaces: Dedicated chart managing all namespaces
- manifests/flux-system: Kustomization for Flux components
- manifests/namespaces: Kustomization for namespaces chart
"""
import os
import subprocess
import tempfile
import time
import re
from pathlib import Path
from typing import Generator, Callable, Dict, Any, List

import pytest
import requests
import yaml


# ============================================================================
# Pytest Hooks
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "gitlab: mark test as requiring GitLab (skipped by default)"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test requiring cluster"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (skipped with -m 'not slow')"
    )


def pytest_collection_modifyitems(config, items):
    """
    Skip gitlab tests unless explicitly requested with -m gitlab.
    GitLab tests are resource-intensive and should be opt-in.
    """
    markexpr = config.getoption("-m", default="")
    if "gitlab" in markexpr:
        return
    
    if os.environ.get("GITLAB_URL"):
        return
    
    skip_gitlab = pytest.mark.skip(
        reason="GitLab tests skipped (use -m gitlab or --profile gitlab to run)"
    )
    for item in items:
        if "gitlab" in item.keywords:
            item.add_marker(skip_gitlab)


# ============================================================================
# Configuration
# ============================================================================

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
GIT_SERVER_URL = os.environ.get("GIT_SERVER_URL", "http://localhost:3000")
KIND_CONFIG_PATH = Path(__file__).parent / "fixtures" / "kind-config.yaml"

# Timeouts (in seconds)
CLUSTER_CREATE_TIMEOUT = 300
DEPLOYMENT_ROLLOUT_TIMEOUT = 180
HELMRELEASE_READY_TIMEOUT = 300
FLUX_SYNC_TIMEOUT = 600


# ============================================================================
# Utility Functions
# ============================================================================

def run_command(
    cmd: List[str],
    timeout: int = 60,
    check: bool = True,
    capture_output: bool = True,
    **kwargs
) -> subprocess.CompletedProcess:
    """Run a command with consistent error handling."""
    try:
        return subprocess.run(
            cmd,
            timeout=timeout,
            check=check,
            capture_output=capture_output,
            text=True,
            **kwargs
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"Command timed out after {timeout}s: {' '.join(cmd)}")
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Command failed: {' '.join(cmd)}\nstderr: {e.stderr}")


def wait_for_condition(
    check_fn: Callable[[], bool],
    timeout: int = 60,
    interval: int = 5,
    description: str = "condition"
) -> bool:
    """Wait for a condition to become true."""
    start = time.time()
    while time.time() - start < timeout:
        if check_fn():
            return True
        time.sleep(interval)
    return False


def _fix_kubeconfig_for_dind(cluster_name: str, kubeconfig_path: str):
    """Fix kubeconfig for Docker-in-Docker setup."""
    try:
        control_plane_name = f"{cluster_name}-control-plane"
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", control_plane_name],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            return
        
        control_plane_ip = result.stdout.strip()
        if not control_plane_ip:
            return
        
        print(f"📍 Control plane IP: {control_plane_ip}")
        
        with open(kubeconfig_path, 'r') as f:
            content = f.read()
        
        fixed_content = re.sub(
            r'server: https://127\.0\.0\.1:\d+',
            f'server: https://{control_plane_ip}:6443',
            content
        )
        
        with open(kubeconfig_path, 'w') as f:
            f.write(fixed_content)
        
        print(f"✅ Fixed kubeconfig to use {control_plane_ip}:6443")
        
    except Exception as e:
        print(f"Warning: Could not fix kubeconfig: {e}")


# ============================================================================
# Kind Cluster Fixtures
# ============================================================================

class KindCluster:
    """Wrapper for kind cluster operations."""
    
    def __init__(self, name: str, kubeconfig: str):
        self.name = name
        self.kubeconfig = kubeconfig
    
    def kubectl(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """Run kubectl command against this cluster."""
        cmd = ["kubectl", "--kubeconfig", self.kubeconfig] + list(args)
        kwargs.setdefault("check", True)
        return run_command(cmd, **kwargs)
    
    def helm(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """Run helm command against this cluster."""
        cmd = ["helm", "--kubeconfig", self.kubeconfig] + list(args)
        kwargs.setdefault("timeout", 300)
        kwargs.setdefault("check", True)
        return run_command(cmd, **kwargs)
    
    def wait_for_deployment(self, name: str, namespace: str, timeout: int = DEPLOYMENT_ROLLOUT_TIMEOUT) -> bool:
        """Wait for a deployment to be available."""
        try:
            self.kubectl(
                "rollout", "status", f"deployment/{name}",
                "-n", namespace, f"--timeout={timeout}s",
                timeout=timeout + 10
            )
            return True
        except:
            return False
    
    def wait_for_helmrelease(self, name: str, namespace: str = "flux-system", timeout: int = HELMRELEASE_READY_TIMEOUT) -> bool:
        """Wait for a HelmRelease to become Ready."""
        def check():
            result = self.kubectl(
                "get", "helmrelease", name, "-n", namespace,
                "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}",
                check=False
            )
            return result.stdout.strip() == "True"
        
        return wait_for_condition(check, timeout=timeout, description=f"HelmRelease {name}")
    
    def wait_for_kustomization(self, name: str, namespace: str = "flux-system", timeout: int = 300) -> bool:
        """Wait for a Kustomization to become Ready."""
        def check():
            result = self.kubectl(
                "get", "kustomization", name, "-n", namespace,
                "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}",
                check=False
            )
            return result.stdout.strip() == "True"
        
        return wait_for_condition(check, timeout=timeout, description=f"Kustomization {name}")


@pytest.fixture(scope="session")
def kind_cluster(request) -> Generator[KindCluster, None, None]:
    """Create a kind cluster for the test session."""
    cluster_name = f"k8s-bootstrap-test-{os.getpid()}"
    kubeconfig_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
    kubeconfig_path = kubeconfig_file.name
    kubeconfig_file.close()
    
    result = subprocess.run(["kind", "get", "clusters"], capture_output=True, text=True)
    cluster_exists = cluster_name in result.stdout.split()
    
    if not cluster_exists:
        print(f"\n🚀 Creating kind cluster: {cluster_name}")
        run_command([
            "kind", "create", "cluster",
            "--name", cluster_name,
            "--config", str(KIND_CONFIG_PATH),
            "--wait", "120s"
        ], timeout=CLUSTER_CREATE_TIMEOUT)
    
    run_command([
        "kind", "export", "kubeconfig",
        "--name", cluster_name,
        "--kubeconfig", kubeconfig_path
    ])
    
    _fix_kubeconfig_for_dind(cluster_name, kubeconfig_path)
    
    cluster = KindCluster(name=cluster_name, kubeconfig=kubeconfig_path)
    
    print("⏳ Waiting for cluster to be ready...")
    for _ in range(30):
        result = cluster.kubectl("get", "nodes", check=False, timeout=30)
        if result.returncode == 0:
            break
        time.sleep(5)
    
    cluster.kubectl("wait", "--for=condition=Ready", "node", "--all", "--timeout=120s", check=False)
    print("✅ Cluster ready!")
    
    yield cluster
    
    keep_cluster = os.environ.get("KEEP_CLUSTER", "0") == "1"
    if not keep_cluster:
        print(f"\n🧹 Deleting kind cluster: {cluster_name}")
        subprocess.run(["kind", "delete", "cluster", "--name", cluster_name])
    
    try:
        os.unlink(kubeconfig_path)
    except:
        pass


# ============================================================================
# Backend API Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def backend_url() -> str:
    """Return the backend API URL."""
    return BACKEND_URL


@pytest.fixture(scope="session")
def api_client(backend_url: str) -> requests.Session:
    """Return a configured requests session for API calls."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    for _ in range(60):
        try:
            response = session.get(f"{backend_url}/api/health", timeout=5)
            if response.status_code == 200:
                break
        except:
            pass
        time.sleep(2)
    else:
        pytest.fail(f"Backend at {backend_url} did not become ready in time")
    
    return session


# ============================================================================
# Bootstrap Generation Fixtures
# ============================================================================

@pytest.fixture
def generate_bootstrap(api_client: requests.Session, backend_url: str, tmp_path: Path, request):
    """
    Factory fixture to generate bootstrap packages via API.
    
    Extracts files from heredocs. For E2E tests (marked with @pytest.mark.e2e),
    also runs vendor-charts.sh to download actual charts.
    
    Generated structure:
    - charts/flux-operator: Wrapper for flux-operator
    - charts/flux-instance: Contains GitRepository, Kustomizations, HelmReleases
    - charts/namespaces: Manages all namespaces
    - charts/<component>: Wrapper charts for each component
    - manifests/flux-system: flux-operator and flux-instance HelmReleases
    - manifests/namespaces: namespaces HelmRelease
    """
    is_e2e = request.node.get_closest_marker("e2e") is not None
    
    def _generate(
        components: List[str],
        cluster_name: str = "test",
        repo_url: str = "git@github.com:test/repo.git",
        branch: str = "main",
        component_values: Dict[str, Dict] = None,
        component_raw_overrides: Dict[str, str] = None,
        git_auth: Dict[str, Any] = None
    ) -> Path:
        comp_list = []
        for comp_id in components:
            comp_data = {"id": comp_id, "enabled": True}
            if component_values and comp_id in component_values:
                comp_data["values"] = component_values[comp_id]
            if component_raw_overrides and comp_id in component_raw_overrides:
                comp_data["raw_overrides"] = component_raw_overrides[comp_id]
            comp_list.append(comp_data)
        
        request_data = {
            "cluster_name": cluster_name,
            "repo_url": repo_url,
            "branch": branch,
            "components": comp_list
        }
        
        if git_auth:
            request_data["git_auth"] = git_auth
        
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json=request_data
        )
        response.raise_for_status()
        
        token = response.json()["token"]
        script_response = api_client.get(f"{backend_url}/bootstrap/{token}")
        script_response.raise_for_status()
        script_content = script_response.text
        
        output_dir = tmp_path / cluster_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract files from heredocs
        heredoc_pattern = r"cat << '([^']+)' > \"([^\"]+)\"\n(.*?)\n\1"
        for eof_marker, path, content in re.findall(heredoc_pattern, script_content, re.DOTALL):
            file_path = output_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        
        # Set executable permissions
        chmod_pattern = r'chmod \+x "([^"]+)"'
        for exec_path in re.findall(chmod_pattern, script_content):
            full_path = output_dir / exec_path
            if full_path.exists():
                os.chmod(full_path, 0o755)
        
        # For E2E tests, run vendor-charts.sh to download actual charts
        if is_e2e:
            vendor_script = output_dir / "vendor-charts.sh"
            if vendor_script.exists():
                print(f"\n📦 Running vendor-charts.sh to download charts...")
                result = run_command(
                    ["bash", str(vendor_script)],
                    cwd=output_dir,
                    timeout=300,
                    check=False
                )
                if result.returncode != 0:
                    print(f"⚠️  vendor-charts.sh failed: {result.stderr}")
                else:
                    print("✓ Charts vendored successfully")
        
        return output_dir
    
    return _generate


# ============================================================================
# Component Definition Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def definitions_path() -> Path:
    """Return path to component definitions."""
    return Path(__file__).parent.parent / "backend" / "definitions" / "components"


@pytest.fixture(scope="session")
def all_definitions(definitions_path: Path) -> Dict[str, Dict]:
    """Load all component definitions."""
    definitions = {}
    for yaml_file in definitions_path.glob("*.yaml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
            definitions[data["id"]] = data
    return definitions


# ============================================================================
# Helm Validation Fixtures
# ============================================================================

@pytest.fixture
def helm_lint():
    """Factory fixture to lint Helm charts."""
    def _lint(chart_path: Path, values: Dict = None) -> subprocess.CompletedProcess:
        cmd = ["helm", "lint", str(chart_path)]
        values_file = None
        
        if values:
            values_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
            yaml.dump(values, values_file)
            values_file.close()
            cmd.extend(["-f", values_file.name])
        
        result = run_command(cmd, check=False)
        
        if values_file:
            os.unlink(values_file.name)
        
        return result
    
    return _lint


@pytest.fixture
def helm_template():
    """Factory fixture to template Helm charts."""
    def _template(
        chart_path: Path,
        release_name: str = "test",
        namespace: str = "default",
        values: Dict = None
    ) -> subprocess.CompletedProcess:
        cmd = ["helm", "template", release_name, str(chart_path), "-n", namespace]
        values_file = None
        
        if values:
            values_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
            yaml.dump(values, values_file)
            values_file.close()
            cmd.extend(["-f", values_file.name])
        
        result = run_command(cmd, check=False)
        
        if values_file:
            os.unlink(values_file.name)
        
        return result
    
    return _template


# ============================================================================
# Git Server Fixtures
# ============================================================================

class GitServer:
    """Wrapper for Git server operations (Gitea)."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.username = "test"
        self.password = "test1234"
        self.email = "test@test.com"
        self._access_token = None
    
    def wait_for_ready(self, timeout: int = 60) -> bool:
        """Wait for Git server to be ready."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = requests.get(f"{self.api_url}/version", timeout=5)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(2)
        return False
    
    def get_or_create_token(self, token_name: str = "pytest-token") -> str:
        """Get or create an access token for API authentication."""
        if self._access_token:
            return self._access_token
        
        try:
            requests.delete(
                f"{self.api_url}/users/{self.username}/tokens/{token_name}",
                auth=(self.username, self.password),
                timeout=10
            )
        except:
            pass
        
        try:
            response = requests.post(
                f"{self.api_url}/users/{self.username}/tokens",
                auth=(self.username, self.password),
                json={"name": token_name, "scopes": ["write:repository", "write:user"]},
                timeout=30
            )
            if response.status_code == 201:
                self._access_token = response.json().get("sha1")
                print(f"✅ Access token created: {self._access_token[:8]}...")
                return self._access_token
        except Exception as e:
            print(f"Could not create token: {e}")
        
        return None
    
    @property
    def access_token(self) -> str:
        """Get access token (creates one if not exists)."""
        if not self._access_token:
            self._access_token = self.get_or_create_token()
        return self._access_token
    
    def create_repo(self, name: str, private: bool = False) -> bool:
        """Create a repository (public or private)."""
        try:
            response = requests.post(
                f"{self.api_url}/user/repos",
                auth=(self.username, self.password),
                json={
                    "name": name,
                    "private": private,
                    "auto_init": False,  # Empty repo
                    "description": f"{'Private' if private else 'Public'} test repository"
                },
                timeout=30
            )
            if response.status_code in [201, 409]:
                visibility = "private" if private else "public"
                print(f"✅ Repository '{name}' ({visibility}) ready")
                return True
            print(f"❌ Failed to create repo: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"Could not create repo: {e}")
            return False
    
    def repo_exists(self, name: str) -> bool:
        """Check if a repository exists."""
        try:
            response = requests.get(
                f"{self.api_url}/repos/{self.username}/{name}",
                auth=(self.username, self.password),
                timeout=10
            )
            return response.status_code == 200
        except:
            return False
    
    def is_repo_private(self, name: str) -> bool:
        """Check if a repository is private."""
        try:
            response = requests.get(
                f"{self.api_url}/repos/{self.username}/{name}",
                auth=(self.username, self.password),
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get("private", False)
        except:
            pass
        return False
    
    def can_access_without_auth(self, name: str) -> bool:
        """Check if repo can be accessed without authentication."""
        try:
            response = requests.get(
                f"{self.api_url}/repos/{self.username}/{name}",
                timeout=10
            )
            return response.status_code == 200
        except:
            return False
    
    def get_repo_url(self, name: str) -> str:
        """Get repository URL (without credentials)."""
        return f"{self.base_url}/{self.username}/{name}.git"
    
    def get_clone_url(self, name: str, use_token: bool = False) -> str:
        """Get clone URL with credentials (password or token)."""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(self.base_url)
        
        if use_token and self.access_token:
            netloc = f"{self.username}:{self.access_token}@{parsed.netloc}"
        else:
            netloc = f"{self.username}:{self.password}@{parsed.netloc}"
        
        return urlunparse((parsed.scheme, netloc, f"/{self.username}/{name}.git", "", "", ""))
    
    def get_auth_config(self) -> Dict[str, Any]:
        """Get authentication configuration for bootstrap."""
        return {
            "enabled": True,
            "platform": "gitea",
            "url": self.base_url,
            "username": self.username,
            "token": self.access_token
        }


@pytest.fixture(scope="session")
def git_server_url() -> str:
    """Return the Git server URL."""
    return GIT_SERVER_URL


@pytest.fixture(scope="session")
def git_server(git_server_url: str) -> Generator[GitServer, None, None]:
    """Get Git server instance with public and private repos."""
    server = GitServer(git_server_url)
    
    if not server.wait_for_ready(timeout=120):
        pytest.skip("Git server not available")
    
    server.get_or_create_token()
    
    server.create_repo("k8s-bootstrap-test", private=False)
    server.create_repo("public-repo", private=False)
    server.create_repo("private-repo", private=True)
    
    if server.can_access_without_auth("private-repo"):
        print("⚠️ Warning: private-repo is accessible without auth")
    else:
        print("✅ private-repo correctly requires authentication")
    
    yield server


@pytest.fixture(scope="session")
def public_repo_url(git_server: GitServer) -> str:
    """Get URL for public test repository."""
    return git_server.get_repo_url("public-repo")


@pytest.fixture(scope="session")
def private_repo_url(git_server: GitServer) -> str:
    """Get URL for private test repository."""
    return git_server.get_repo_url("private-repo")


@pytest.fixture(scope="session")
def git_auth_config(git_server: GitServer) -> Dict[str, Any]:
    """Get Git authentication configuration for private repos."""
    return git_server.get_auth_config()
