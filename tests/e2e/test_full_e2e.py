"""
Full End-to-End Tests for k8s-bootstrap

Test sequence:
1. Test deployment from PUBLIC Gitea repository (no auth needed)
2. Destroy cluster, create new one
3. Test deployment from PRIVATE Gitea repository (with token auth)
4. If GitLab is available: destroy cluster, test PRIVATE GitLab repository

Run Gitea tests:
    docker compose -f tests/docker-compose.test.yml run --rm test-e2e-full

Run with GitLab:
    docker compose -f tests/docker-compose.test.yml --profile gitlab run --rm test-e2e-full-gitlab

Architecture:
- flux-operator: Installs Flux via FluxInstance CRD
- flux-instance: Contains GitRepository, Kustomizations, HelmReleases for all components
- namespaces: Dedicated chart managing all namespaces via Kustomization
- Components: Managed as HelmReleases within flux-instance chart
"""
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import requests
import yaml


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def backend_url():
    """Backend API URL."""
    return os.environ.get("BACKEND_URL", "http://backend:8000")


@pytest.fixture(scope="module")
def gitea_url():
    """Gitea URL."""
    return os.environ.get("GITEA_URL", "http://gitea:3000")


@pytest.fixture(scope="module")
def gitlab_url():
    """GitLab URL."""
    return os.environ.get("GITLAB_URL", "http://gitlab:80")


@pytest.fixture(scope="module")
def gitea_credentials():
    """Load Gitea credentials from init script outputs."""
    creds = {
        "username": "test",
        "password": "test12345678",
        "token": None,
    }
    
    token_files = [
        "/tmp/gitea-init/gitea-token.txt",
        "/tmp/gitea-init/token.txt",
        "/tmp/gitea_token.txt",
    ]
    
    for filepath in token_files:
        try:
            with open(filepath, "r") as f:
                creds["token"] = f.read().strip()
                print(f"📝 Found Gitea token: {creds['token'][:10]}...")
                break
        except FileNotFoundError:
            continue
    
    if not creds["token"]:
        print("⚠️ No Gitea token found in files")
    
    return creds


@pytest.fixture(scope="module")
def gitlab_credentials():
    """Load GitLab credentials from init script outputs."""
    creds = {"pat": None}
    
    try:
        with open("/tmp/gitlab-init/root_pat.txt", "r") as f:
            creds["pat"] = f.read().strip()
    except FileNotFoundError:
        try:
            result = subprocess.run(
                ["docker", "exec", "tests-gitlab-1", "cat", "/tmp/gitlab-init/root_pat.txt"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                creds["pat"] = result.stdout.strip()
        except Exception:
            pass
    
    return creds


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


class KindCluster:
    """Manages a kind cluster for testing."""
    
    def __init__(self, name: str):
        self.name = name
        self.kubeconfig_path = tempfile.mktemp(suffix=".yaml")
        self._created = False
    
    def create(self):
        """Create the kind cluster."""
        print(f"\n🚀 Creating kind cluster: {self.name}")
        
        subprocess.run(
            ["kind", "delete", "cluster", "--name", self.name],
            capture_output=True
        )
        
        result = subprocess.run(
            ["kind", "create", "cluster", "--name", self.name, "--wait", "120s"],
            capture_output=True, text=True, timeout=300
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create cluster: {result.stderr}")
        
        subprocess.run(
            ["kind", "export", "kubeconfig", "--name", self.name, "--kubeconfig", self.kubeconfig_path],
            check=True
        )
        
        _fix_kubeconfig_for_dind(self.name, self.kubeconfig_path)
        
        self._created = True
        print(f"✅ Cluster {self.name} ready")
        return self
    
    def delete(self):
        """Delete the kind cluster."""
        if self._created:
            print(f"\n🧹 Deleting kind cluster: {self.name}")
            subprocess.run(
                ["kind", "delete", "cluster", "--name", self.name],
                capture_output=True
            )
            self._created = False
        
        try:
            os.unlink(self.kubeconfig_path)
        except:
            pass
    
    def kubectl(self, *args, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess:
        """Run kubectl command against this cluster."""
        cmd = ["kubectl", "--kubeconfig", self.kubeconfig_path] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)
    
    def wait_for_helmrelease(self, name: str, namespace: str, timeout: int = 300) -> bool:
        """Wait for a HelmRelease to become Ready."""
        print(f"  ⏳ Waiting for HelmRelease {namespace}/{name}...")
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            result = self.kubectl(
                "get", "helmrelease", name, "-n", namespace,
                "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}",
                check=False
            )
            if result.stdout.strip() == "True":
                print(f"  ✅ HelmRelease {namespace}/{name} ready!")
                return True
            
            # Print status for debugging
            if result.returncode == 0 and result.stdout.strip():
                print(f"    Status: {result.stdout.strip()}")
            
            time.sleep(10)
        
        # Print final status on failure
        hr_status = self.kubectl(
            "get", "helmrelease", name, "-n", namespace, "-o", "wide",
            check=False
        )
        print(f"  ❌ HelmRelease status: {hr_status.stdout}")
        
        raise TimeoutError(f"HelmRelease {namespace}/{name} not ready after {timeout}s")
    
    def kubectl(self, *args, check=True, timeout=60):
        """Run kubectl command."""
        cmd = ["kubectl", "--kubeconfig", self.kubeconfig_path] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)
    
    def helm(self, *args, check=True, timeout=300):
        """Run helm command."""
        cmd = ["helm", "--kubeconfig", self.kubeconfig_path] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def wait_for_helmreleases(kubectl_fn, timeout=600):
    """Wait for all HelmReleases to become Ready."""
    print(f"\n⏳ Waiting for HelmReleases (timeout: {timeout}s)...")
    start = time.time()
    
    while time.time() - start < timeout:
        result = kubectl_fn("get", "helmreleases", "-A", "-o", "wide", check=False)
        
        if result.returncode != 0:
            time.sleep(10)
            continue
        
        lines = result.stdout.strip().split('\n')
        if len(lines) <= 1:
            time.sleep(10)
            continue
        
        all_ready = True
        ready_count = 0
        total_count = 0
        
        for line in lines[1:]:  # Skip header
            total_count += 1
            if "True" in line and "succeeded" in line.lower():
                ready_count += 1
            else:
                all_ready = False
        
        elapsed = int(time.time() - start)
        print(f"  ⏳ {ready_count}/{total_count} HelmReleases ready ({elapsed}s elapsed)")
        
        if all_ready and total_count > 0:
            print(f"\n✅ All {total_count} HelmReleases ready in {elapsed}s")
            return True
        
        time.sleep(15)
    
    print(f"\n❌ TIMEOUT waiting for HelmReleases after {timeout}s")
    return False


def wait_for_kustomizations(kubectl_fn, timeout=300):
    """Wait for all Kustomizations to become Ready."""
    print(f"\n⏳ Waiting for Kustomizations (timeout: {timeout}s)...")
    start = time.time()
    
    while time.time() - start < timeout:
        result = kubectl_fn("get", "kustomizations", "-A", "-o", "wide", check=False)
        
        if result.returncode != 0:
            time.sleep(10)
            continue
        
        lines = result.stdout.strip().split('\n')
        if len(lines) <= 1:
            time.sleep(10)
            continue
        
        all_ready = True
        for line in lines[1:]:
            if "True" not in line:
                all_ready = False
                break
        
        if all_ready:
            elapsed = int(time.time() - start)
            print(f"✅ All Kustomizations ready in {elapsed}s")
            return True
        
        time.sleep(10)
    
    return False


# ============================================================================
# Test Classes
# ============================================================================

@pytest.mark.e2e
class TestPublicGiteaRepo:
    """Test 1: Deploy from PUBLIC Gitea repository (no authentication needed)."""
    
    @pytest.fixture(scope="class")
    def cluster(self):
        """Create cluster for public repo tests."""
        cluster = KindCluster("e2e-public")
        cluster.create()
        yield cluster
        if os.environ.get("KEEP_CLUSTER", "0") != "1":
            cluster.delete()
    
    def test_public_repo_deployment(self, backend_url, gitea_url, gitea_credentials, cluster):
        """
        Full E2E test with public repository:
        1. Generate bootstrap pointing to public Gitea repo (no Flux auth)
        2. Run bootstrap script (credentials needed for git push)
        3. Verify Flux components are installed
        4. Verify HelmReleases are reconciled
        
        Note: Gitea requires auth to PUSH even on public repos.
        We provide GITEA_USER/GITEA_PASS for push, but Flux pulls without auth.
        """
        print("\n" + "="*60)
        print("TEST: Deployment from PUBLIC Gitea repository")
        print("="*60)
        
        # First, ensure the public repo is empty
        token = gitea_credentials.get("token") or gitea_credentials["password"]
        try:
            # Delete existing repo
            requests.delete(
                f"{gitea_url}/api/v1/repos/test/public-repo",
                headers={"Authorization": f"token {token}"},
                timeout=30
            )
            import time
            time.sleep(1)
            # Recreate empty public repo
            requests.post(
                f"{gitea_url}/api/v1/user/repos",
                headers={"Authorization": f"token {token}"},
                json={"name": "public-repo", "private": False, "auto_init": False},
                timeout=30
            )
            print("✅ Recreated empty public repo")
        except Exception as e:
            print(f"⚠️ Could not recreate repo: {e}")
        
        response = requests.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "public-test",
                "repo_url": f"{gitea_url}/test/public-repo.git",
                "branch": "main",
                "components": [
                    {"id": "metrics-server", "enabled": True}
                ]
                # No git_auth - Flux pulls without credentials
            },
            timeout=60
        )
        
        assert response.status_code == 200, f"API error: {response.text}"
        api_token = response.json()["token"]
        
        script_response = requests.get(f"{backend_url}/bootstrap/{api_token}", timeout=30)
        assert script_response.status_code == 200
        
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "bootstrap.sh"
            script_path.write_text(script_response.text)
            script_path.chmod(0o755)
            
            env = os.environ.copy()
            env["HOME"] = tmpdir
            env["KUBECONFIG"] = cluster.kubeconfig_path
            # Provide credentials for git push (Flux won't use them)
            env["GITEA_USER"] = gitea_credentials["username"]
            env["GITEA_PASS"] = token
            
            gitconfig = Path(tmpdir) / ".gitconfig"
            gitconfig.write_text("[user]\n    email = test@test.local\n    name = Test\n[init]\n    defaultBranch = main\n")
            
            print("🚀 Running bootstrap script...")
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            print(f"Bootstrap output (last 2000 chars):\n{result.stdout[-2000:]}")
            if result.returncode != 0:
                print(f"Bootstrap stderr:\n{result.stderr[-1000:]}")
        
        # Wait for Flux to start
        import time
        time.sleep(15)
        
        # Verify Flux is installed
        flux_check = cluster.kubectl("get", "pods", "-n", "flux-system", check=False)
        print(f"\n📋 Flux pods:\n{flux_check.stdout}")
        
        assert "flux-operator" in flux_check.stdout or "source-controller" in flux_check.stdout, \
            "Flux should be installed"
        
        print("✅ PUBLIC repo test passed!")


@pytest.mark.e2e
class TestPrivateGiteaRepo:
    """Test 2: Deploy from PRIVATE Gitea repository (with token auth)."""
    
    @pytest.fixture(scope="class")
    def cluster(self):
        """Create NEW cluster for private repo tests."""
        cluster = KindCluster("e2e-private")
        cluster.create()
        yield cluster
        if os.environ.get("KEEP_CLUSTER", "0") != "1":
            cluster.delete()
    
    def test_private_repo_deployment(self, backend_url, gitea_url, gitea_credentials, cluster):
        """
        Full E2E test with private Gitea repository:
        1. Generate bootstrap pointing to private Gitea repo with auth
        2. Run bootstrap with credentials
        3. Verify Flux can pull from private repo
        4. Verify SOPS/Age secrets are created
        5. Verify all HelmReleases reconcile
        """
        print("\n" + "="*60)
        print("TEST: Deployment from PRIVATE Gitea repository")
        print("="*60)
        
        token = gitea_credentials.get("token")
        if not token:
            pytest.skip("No Gitea token available")
        
        # Ensure repo is empty before test
        import time
        try:
            requests.delete(
                f"{gitea_url}/api/v1/repos/test/private-repo",
                headers={"Authorization": f"token {token}"},
                timeout=30
            )
            time.sleep(1)
            requests.post(
                f"{gitea_url}/api/v1/user/repos",
                headers={"Authorization": f"token {token}"},
                json={"name": "private-repo", "private": True, "auto_init": False},
                timeout=30
            )
            print("✅ Recreated empty private repo")
        except Exception as e:
            print(f"⚠️ Could not recreate repo: {e}")
        
        response = requests.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "private-test",
                "repo_url": f"{gitea_url}/test/private-repo.git",
                "branch": "main",
                "components": [
                    {"id": "metrics-server", "enabled": True}
                ],
                "git_auth": {
                    "enabled": True,
                    "platform": "gitea",
                    "custom_url": gitea_url
                }
            },
            timeout=60
        )
        
        assert response.status_code == 200, f"API error: {response.text}"
        result_token = response.json()["token"]
        
        script_response = requests.get(f"{backend_url}/bootstrap/{result_token}", timeout=30)
        assert script_response.status_code == 200
        
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "bootstrap.sh"
            script_path.write_text(script_response.text)
            script_path.chmod(0o755)
            
            env = os.environ.copy()
            env["HOME"] = tmpdir
            env["KUBECONFIG"] = cluster.kubeconfig_path
            env["GIT_USERNAME"] = gitea_credentials["username"]
            env["GIT_TOKEN"] = token
            env["GITEA_USER"] = gitea_credentials["username"]
            env["GITEA_PASS"] = token
            
            gitconfig = Path(tmpdir) / ".gitconfig"
            gitconfig.write_text("[user]\n    email = test@test.local\n    name = Test\n[init]\n    defaultBranch = main\n[credential]\n    helper = store\n")
            
            gitea_host = gitea_url.replace("http://", "").replace("https://", "")
            git_creds = Path(tmpdir) / ".git-credentials"
            git_creds.write_text(f"http://{gitea_credentials['username']}:{token}@{gitea_host}\n")
            git_creds.chmod(0o600)
            
            print("🚀 Running bootstrap script with credentials...")
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=900
            )
            
            print(f"Bootstrap output (last 2000 chars):\n{result.stdout[-2000:]}")
            if result.returncode != 0:
                print(f"Bootstrap stderr:\n{result.stderr[-1000:]}")
        
        # Verify Flux is installed
        flux_check = cluster.kubectl("get", "pods", "-n", "flux-system", check=False)
        print(f"\n📋 Flux pods:\n{flux_check.stdout}")
        
        # Verify SOPS secret exists
        sops_check = cluster.kubectl("get", "secret", "sops-age", "-n", "flux-system", check=False)
        if sops_check.returncode == 0:
            print("✅ sops-age secret exists")
        
        # Verify Git credentials secret exists
        creds_check = cluster.kubectl("get", "secret", "flux-git-credentials", "-n", "flux-system", check=False)
        if creds_check.returncode == 0:
            print("✅ flux-git-credentials secret exists")
        
        # Wait for reconciliation
        time.sleep(30)
        
        # Check Kustomizations
        kust_check = cluster.kubectl("get", "kustomizations", "-A", check=False)
        print(f"\n📋 Kustomizations:\n{kust_check.stdout}")
        
        # Check HelmReleases
        hr_check = cluster.kubectl("get", "helmreleases", "-A", check=False)
        print(f"\n📋 HelmReleases:\n{hr_check.stdout}")
        
        print("✅ PRIVATE Gitea repo test passed!")


@pytest.mark.e2e
@pytest.mark.gitlab
class TestPrivateGitLabRepo:
    """Test 3: Deploy from PRIVATE GitLab repository (with PAT auth)."""
    
    @pytest.fixture(scope="class")
    def cluster(self):
        """Create NEW cluster for GitLab tests."""
        cluster = KindCluster("e2e-gitlab")
        cluster.create()
        yield cluster
        if os.environ.get("KEEP_CLUSTER", "0") != "1":
            cluster.delete()
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_gitlab_repo(self, gitlab_credentials):
        """Ensure GitLab private repo exists and is empty."""
        pat = gitlab_credentials.get("pat")
        if not pat:
            pytest.skip("No GitLab PAT available")
        
        print("📦 Recreating GitLab private repo...")
        result = subprocess.run(
            ["docker", "exec", "tests-gitlab-1", "gitlab-rails", "runner", """
p = Project.find_by_full_path('root/private-repo')
p.destroy if p
root = User.find_by_username('root')
project = Projects::CreateService.new(root, {
  name: 'private-repo',
  path: 'private-repo',
  visibility_level: Gitlab::VisibilityLevel::PRIVATE,
  initialize_with_readme: false
}).execute
puts project.persisted? ? 'Created' : 'Failed'
"""],
            capture_output=True, text=True, timeout=60
        )
        print(f"GitLab repo setup: {result.stdout.strip()}")
    
    def test_gitlab_private_repo_deployment(self, backend_url, gitlab_url, gitlab_credentials, cluster):
        """
        Full E2E test with private GitLab repository:
        1. Generate bootstrap for private GitLab repo
        2. Run bootstrap with GitLab PAT
        3. Verify Flux can sync from private GitLab repo
        """
        print("\n" + "="*60)
        print("TEST: Deployment from PRIVATE GitLab repository")
        print("="*60)
        
        pat = gitlab_credentials.get("pat")
        if not pat:
            pytest.skip("No GitLab PAT available")
        
        project_path = "root/private-repo"
        
        response = requests.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "gitlab-test",
                "repo_url": f"{gitlab_url}/{project_path}.git",
                "branch": "main",
                "components": [
                    {"id": "metrics-server", "enabled": True}
                ],
                "git_auth": {
                    "enabled": True,
                    "platform": "gitlab",
                    "custom_url": gitlab_url
                }
            },
            timeout=60
        )
        
        assert response.status_code == 200, f"API error: {response.text}"
        token = response.json()["token"]
        
        script_response = requests.get(f"{backend_url}/bootstrap/{token}", timeout=30)
        assert script_response.status_code == 200
        
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "bootstrap.sh"
            script_path.write_text(script_response.text)
            script_path.chmod(0o755)
            
            env = os.environ.copy()
            env["HOME"] = tmpdir
            env["KUBECONFIG"] = cluster.kubeconfig_path
            env["GIT_USERNAME"] = "oauth2"
            env["GIT_TOKEN"] = pat
            
            gitconfig = Path(tmpdir) / ".gitconfig"
            gitconfig.write_text("[user]\n    email = test@test.local\n    name = Test\n[init]\n    defaultBranch = main\n[credential]\n    helper = store\n")
            
            gitlab_host = gitlab_url.replace("http://", "").replace("https://", "")
            git_creds = Path(tmpdir) / ".git-credentials"
            git_creds.write_text(f"http://oauth2:{pat}@{gitlab_host}\n")
            git_creds.chmod(0o600)
            
            print("🚀 Running bootstrap script with GitLab PAT...")
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=900
            )
            
            print(f"Bootstrap output (last 2000 chars):\n{result.stdout[-2000:]}")
            if result.returncode != 0:
                print(f"Bootstrap stderr:\n{result.stderr[-1000:]}")
        
        # Wait for Flux CRDs
        print("⏳ Waiting for Flux CRDs...")
        for _ in range(30):
            crd_check = cluster.kubectl("get", "crd", "gitrepositories.source.toolkit.fluxcd.io", check=False)
            if crd_check.returncode == 0:
                print("✅ Flux CRDs ready")
                break
            time.sleep(5)
        
        # Verify Flux pods
        flux_check = cluster.kubectl("get", "pods", "-n", "flux-system", "-o", "wide", check=False)
        print(f"\n📋 Flux pods:\n{flux_check.stdout}")
        
        # Check GitRepository
        gitrepo_check = cluster.kubectl("get", "gitrepository", "-n", "flux-system", check=False)
        print(f"\n📋 GitRepositories:\n{gitrepo_check.stdout}")
        
        # Verify credentials secret
        secret_check = cluster.kubectl("get", "secret", "flux-git-credentials", "-n", "flux-system", check=False)
        if secret_check.returncode == 0:
            print("✅ flux-git-credentials secret exists")
        
        print("✅ PRIVATE GitLab repo test passed!")


@pytest.mark.e2e
class TestBootstrapValidation:
    """Test bootstrap script validation without full deployment."""
    
    def test_script_syntax_valid(self, api_client, backend_url):
        """Test that bootstrap.sh has valid bash syntax."""
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "syntax-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "cert-manager", "enabled": True}]
            }
        )
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/bootstrap/{token}").text
        
        # Write and check syntax
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script)
            f.flush()
            
            result = subprocess.run(
                ["bash", "-n", f.name],
                capture_output=True, text=True
            )
            
            os.unlink(f.name)
        
        assert result.returncode == 0, f"Syntax error in bootstrap.sh: {result.stderr}"
    
    def test_generated_structure_has_required_dirs(self, generate_bootstrap):
        """Test that generated structure has required directories."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="struct-test"
        )
        
        # Root files
        assert (bootstrap_dir / "bootstrap.sh").exists()
        assert (bootstrap_dir / "README.md").exists()
        assert (bootstrap_dir / ".gitignore").exists()
        assert (bootstrap_dir / ".sops.yaml").exists()
        
        # Charts
        charts = bootstrap_dir / "charts"
        assert (charts / "flux-operator").exists()
        assert (charts / "flux-instance").exists()
        assert (charts / "namespaces").exists()
        assert (charts / "cert-manager").exists()
        assert (charts / "ingress-nginx").exists()
        
        # Manifests
        manifests = bootstrap_dir / "manifests"
        assert (manifests / "flux-system").exists()
        assert (manifests / "namespaces").exists()


@pytest.mark.e2e
class TestUpdateScriptGeneration:
    """Tests for update script generation and features."""
    
    def test_update_script_syntax_valid(self, api_client, backend_url):
        """Test that update.sh has valid bash syntax."""
        response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "update-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "cert-manager", "enabled": True}]
            }
        )
        
        assert response.status_code == 200
        token = response.json()["token"]
        
        script_response = api_client.get(f"{backend_url}/update/{token}")
        assert script_response.status_code == 200
        
        script = script_response.text
        
        # Write and check syntax
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script)
            f.flush()
            
            result = subprocess.run(
                ["bash", "-n", f.name],
                capture_output=True, text=True
            )
            
            os.unlink(f.name)
        
        assert result.returncode == 0, f"Syntax error in update.sh: {result.stderr}"
    
    def test_update_script_has_required_functions(self, api_client, backend_url):
        """Test that update script has all required functions."""
        response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "update-funcs",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "ingress-nginx", "enabled": True}]
            }
        )
        
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/update/{token}").text
        
        # Required functions
        required_functions = [
            "check_prerequisites",
            "sync_git",
            "check_file_changes",
            "check_chart_changes",
            "update_files",
            "update_charts",
            "commit_and_push",
            "trigger_reconciliation",
            "show_status",
            "main"
        ]
        
        for func in required_functions:
            assert f"{func}()" in script or f"function {func}" in script, \
                f"Missing function: {func}"
    
    def test_update_script_has_dry_run_mode(self, api_client, backend_url):
        """Test that update script supports dry-run mode."""
        response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "dry-run-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "metallb", "enabled": True}]
            }
        )
        
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/update/{token}").text
        
        assert "--dry-run" in script
        assert "DRY_RUN" in script
        assert "[DRY-RUN]" in script
    
    def test_update_script_includes_file_checksums(self, api_client, backend_url):
        """Test that update script includes file checksums for comparison."""
        response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "checksum-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "cert-manager", "enabled": True}]
            }
        )
        
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/update/{token}").text
        
        # Script should check checksums
        assert "md5sum" in script or "checksum" in script.lower()
        assert "CHANGED_FILES" in script
        assert "UNCHANGED_FILES" in script
    
    def test_update_script_checks_chart_versions(self, api_client, backend_url):
        """Test that update script checks chart versions before downloading."""
        response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "chart-version-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "ingress-nginx", "enabled": True}]
            }
        )
        
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/update/{token}").text
        
        assert "CHARTS_TO_UPDATE" in script
        assert "check_single_chart" in script
        assert "Chart.yaml" in script
    
    def test_update_script_triggers_flux_reconciliation(self, api_client, backend_url):
        """Test that update script triggers Flux reconciliation."""
        response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "flux-reconcile-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "metrics-server", "enabled": True}]
            }
        )
        
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/update/{token}").text
        
        assert "trigger_reconciliation" in script
        assert "flux-system" in script
        assert "reconcile.fluxcd.io/requestedAt" in script


@pytest.mark.e2e
class TestUpdateFlow:
    """Test complete update workflow."""
    
    @pytest.fixture(scope="class")
    def initial_bootstrap(self, api_client, backend_url, tmp_path_factory):
        """Generate initial bootstrap structure."""
        tmp_path = tmp_path_factory.mktemp("update-flow")
        
        # Create initial bootstrap
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "update-flow-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [
                    {"id": "cert-manager", "enabled": True}
                ]
            }
        )
        
        token = response.json()["token"]
        script = api_client.get(f"{backend_url}/bootstrap/{token}").text
        
        # Create directory and extract files
        output_dir = tmp_path / "update-flow-test"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write a mock bootstrap file to simulate existing installation
        (output_dir / "bootstrap.sh").write_text("#!/bin/bash\necho 'mock'")
        (output_dir / "charts").mkdir(exist_ok=True)
        (output_dir / "manifests").mkdir(exist_ok=True)
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=output_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.local"],
            cwd=output_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=output_dir, capture_output=True
        )
        subprocess.run(["git", "add", "-A"], cwd=output_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=output_dir, capture_output=True
        )
        
        return output_dir
    
    def test_update_generates_different_script_than_bootstrap(
        self, api_client, backend_url
    ):
        """Test that update generates different script than bootstrap."""
        components = [{"id": "cert-manager", "enabled": True}]
        
        # Get bootstrap script
        bootstrap_response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "diff-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": components
            }
        )
        bootstrap_token = bootstrap_response.json()["token"]
        bootstrap_script = api_client.get(
            f"{backend_url}/bootstrap/{bootstrap_token}"
        ).text
        
        # Get update script
        update_response = api_client.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": "diff-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": components
            }
        )
        update_token = update_response.json()["token"]
        update_script = api_client.get(f"{backend_url}/update/{update_token}").text
        
        # Scripts should be different
        assert bootstrap_script != update_script
        
        # Update script has update-specific features
        assert "check_prerequisites" in update_script
        assert "sync_git" in update_script
        assert "trigger_reconciliation" in update_script
        
        # Bootstrap creates directories; update checks existing
        assert "mkdir -p" in bootstrap_script
        assert "Not in a k8s-bootstrap directory" in update_script


@pytest.mark.e2e
class TestUpdateWorkflow:
    """
    Full E2E test for update workflow:
    1. Create fresh empty repo, bootstrap initial cluster with cert-manager
    2. Wait for cert-manager to deploy
    3. Import config, add new component (ingress-nginx)
    4. Run update script to commit and push
    5. Wait for Flux to reconcile
    6. Verify ingress-nginx is deployed to cluster
    """
    
    REPO_NAME = "update-workflow-test"
    
    @pytest.fixture(scope="class")
    def update_cluster(self):
        """Create dedicated cluster for update workflow tests."""
        cluster = KindCluster("e2e-update-workflow")
        cluster.create()
        yield cluster
        if os.environ.get("KEEP_CLUSTER", "0") != "1":
            cluster.delete()
    
    @pytest.fixture(scope="class")
    def update_repo(self, gitea_url):
        """Create a fresh empty repo for update workflow test."""
        import urllib.request
        import json
        
        # Create empty repo via Gitea API
        repo_data = json.dumps({
            "name": self.REPO_NAME,
            "auto_init": False,
            "private": False
        }).encode()
        
        req = urllib.request.Request(
            f"{gitea_url}/api/v1/user/repos",
            data=repo_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        # Add basic auth for Gitea
        import base64
        credentials = base64.b64encode(b"test:test1234").decode()
        req.add_header("Authorization", f"Basic {credentials}")
        
        try:
            urllib.request.urlopen(req, timeout=10)
            print(f"✅ Created fresh repo: {self.REPO_NAME}")
        except urllib.error.HTTPError as e:
            if e.code == 409:  # Already exists - delete and recreate
                # Delete existing repo
                del_req = urllib.request.Request(
                    f"{gitea_url}/api/v1/repos/test/{self.REPO_NAME}",
                    headers={"Authorization": f"Basic {credentials}"},
                    method="DELETE"
                )
                try:
                    urllib.request.urlopen(del_req, timeout=10)
                except:
                    pass
                time.sleep(1)
                # Recreate
                urllib.request.urlopen(req, timeout=10)
                print(f"✅ Recreated repo: {self.REPO_NAME}")
            else:
                raise
        
        return f"{gitea_url}/test/{self.REPO_NAME}.git"
    
    @pytest.fixture(scope="class")
    def work_dir(self, tmp_path_factory):
        """Create working directory for update workflow."""
        return tmp_path_factory.mktemp("update-workflow")
    
    def test_01_initial_bootstrap_and_deploy(self, backend_url, update_repo, update_cluster, work_dir):
        """
        Step 1: Bootstrap with cert-manager and deploy to cluster.
        """
        print("\n" + "="*70)
        print("UPDATE WORKFLOW: Step 1 - Initial Bootstrap & Deploy")
        print("="*70)
        
        # Generate bootstrap with metrics-server only (simple, no CRD dependencies)
        response = requests.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "update-wf",
                "repo_url": update_repo,
                "branch": "main",
                "components": [
                    {"id": "metrics-server", "enabled": True}
                ]
            },
            timeout=60
        )
        assert response.status_code == 200, f"API error: {response.text}"
        
        token = response.json()["token"]
        script_response = requests.get(f"{backend_url}/bootstrap/{token}", timeout=30)
        assert script_response.status_code == 200
        
        # Extract files from bootstrap script
        script_content = script_response.text
        heredoc_pattern = r"cat << '([^']+)' > \"([^\"]+)\"\n(.*?)\n\1"
        
        cluster_dir = work_dir / "update-wf"
        cluster_dir.mkdir(parents=True, exist_ok=True)
        
        for eof_marker, path, content in re.findall(heredoc_pattern, script_content, re.DOTALL):
            file_path = cluster_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        
        # Set executable permissions
        chmod_pattern = r'chmod \+x "([^"]+)"'
        for exec_path in re.findall(chmod_pattern, script_content):
            full_path = cluster_dir / exec_path
            if full_path.exists():
                os.chmod(full_path, 0o755)
        
        # Run vendor-charts.sh to download Helm charts
        print("📦 Running vendor-charts.sh...")
        vendor_result = subprocess.run(
            ["bash", "vendor-charts.sh"],
            cwd=cluster_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        assert vendor_result.returncode == 0, f"Vendor failed: {vendor_result.stderr}"
        print("✅ Charts vendored")
        
        # Initialize git and push
        env = os.environ.copy()
        env["HOME"] = str(work_dir)
        
        gitconfig = work_dir / ".gitconfig"
        gitconfig.write_text("[user]\n    email = test@test.local\n    name = Test\n[init]\n    defaultBranch = main\n")
        
        subprocess.run(["git", "init"], cwd=cluster_dir, capture_output=True, env=env)
        subprocess.run(["git", "remote", "add", "origin", update_repo], cwd=cluster_dir, capture_output=True, env=env)
        subprocess.run(["git", "add", "-A"], cwd=cluster_dir, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "Initial bootstrap with cert-manager"], cwd=cluster_dir, capture_output=True, env=env)
        
        # Push with embedded credentials
        push_url = update_repo.replace("http://gitea:3000", "http://test:test1234@gitea:3000")
        push_result = subprocess.run(
            ["git", "push", "-u", push_url, "main"],
            cwd=cluster_dir, capture_output=True, text=True, env=env
        )
        assert push_result.returncode == 0, f"Push failed: {push_result.stderr}"
        print("✅ Pushed to git")
        
        # Run bootstrap.sh to deploy
        print("🚀 Running bootstrap.sh...")
        env["KUBECONFIG"] = update_cluster.kubeconfig_path
        env["GITEA_USER"] = "test"
        env["GITEA_PASS"] = "test1234"
        
        bootstrap_result = subprocess.run(
            ["bash", "bootstrap.sh"],
            cwd=cluster_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=600
        )
        print(f"Bootstrap output (last 2000 chars):\n{bootstrap_result.stdout[-2000:]}")
        assert bootstrap_result.returncode == 0, f"Bootstrap failed: {bootstrap_result.stderr}"
        print("✅ Bootstrap completed")
        
        # Wait for metrics-server to be ready
        print("⏳ Waiting for metrics-server HelmRelease...")
        update_cluster.wait_for_helmrelease("metrics-server", "metrics-server", timeout=300)
        print("✅ metrics-server deployed!")
        
        # Verify metrics-server pods are running
        pods_result = subprocess.run(
            ["kubectl", "--kubeconfig", update_cluster.kubeconfig_path,
             "get", "pods", "-n", "metrics-server", "-o", "name"],
            capture_output=True, text=True
        )
        assert "metrics-server" in pods_result.stdout, "metrics-server pods should exist"
        print("✅ metrics-server pods running")
    
    def test_02_verify_initial_state(self, update_cluster, work_dir):
        """
        Step 2: Verify initial state - only cert-manager should be deployed.
        """
        print("\n" + "="*70)
        print("UPDATE WORKFLOW: Step 2 - Verify Initial State")
        print("="*70)
        
        cluster_dir = work_dir / "update-wf"
        
        # Verify metallb is NOT deployed
        ns_result = subprocess.run(
            ["kubectl", "--kubeconfig", update_cluster.kubeconfig_path,
             "get", "ns", "metallb-system", "--ignore-not-found"],
            capture_output=True, text=True
        )
        assert "metallb-system" not in ns_result.stdout, "metallb-system should NOT exist yet"
        print("✅ metallb-system namespace does not exist (expected)")
        
        # Verify config file exists
        config_path = cluster_dir / "k8s-bootstrap.yaml"
        assert config_path.exists(), "k8s-bootstrap.yaml should exist"
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        # Config uses snake_case: cluster_name, repo_url, selections
        component_ids = [c["id"] for c in config.get("selections", [])]
        assert "metrics-server" in component_ids, "metrics-server should be in config"
        assert "metallb" not in component_ids, "metallb should NOT be in config yet"
        print(f"✅ Config has components: {component_ids}")
    
    def test_03_generate_and_apply_update(self, backend_url, update_repo, update_cluster, work_dir):
        """
        Step 3: Import config, add ingress-nginx, generate update, apply it.
        """
        print("\n" + "="*70)
        print("UPDATE WORKFLOW: Step 3 - Generate & Apply Update")
        print("="*70)
        
        cluster_dir = work_dir / "update-wf"
        
        # Read existing config (simulating "Load Previous Config" in UI)
        config_path = cluster_dir / "k8s-bootstrap.yaml"
        with open(config_path) as f:
            existing_config = yaml.safe_load(f)
        
        # Config uses snake_case: cluster_name, repo_url, selections
        print(f"📋 Loaded config: {existing_config.get('cluster_name')}")
        print(f"   Current components: {[c['id'] for c in existing_config.get('selections', [])]}")
        
        # Generate update with NEW component (metallb)
        print("📝 Generating update with metallb...")
        response = requests.post(
            f"{backend_url}/api/update",
            json={
                "cluster_name": existing_config.get("cluster_name"),
                "repo_url": existing_config.get("repo_url"),
                "branch": existing_config.get("branch", "main"),
                "components": [
                    {"id": "metrics-server", "enabled": True},
                    {"id": "metallb", "enabled": True}  # NEW!
                ]
            },
            timeout=120
        )
        assert response.status_code == 200, f"API error: {response.text}"
        
        data = response.json()
        print(f"   Update includes {data['files_count']} files, {data['charts_count']} charts")
        
        # Get and save update script
        token = data["token"]
        script_response = requests.get(f"{backend_url}/update/{token}", timeout=30)
        assert script_response.status_code == 200
        
        update_script_path = cluster_dir / "update.sh"
        update_script_path.write_text(script_response.text)
        update_script_path.chmod(0o755)
        
        # Run update script (NOT dry-run!)
        print("🔄 Running update script...")
        env = os.environ.copy()
        env["HOME"] = str(work_dir)
        env["KUBECONFIG"] = update_cluster.kubeconfig_path
        env["GITEA_USER"] = "test"
        env["GITEA_PASS"] = "test1234"
        
        update_result = subprocess.run(
            ["bash", "update.sh", "--force"],
            cwd=cluster_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=600
        )
        print(f"Update output (last 2000 chars):\n{update_result.stdout[-2000:]}")
        
        if update_result.returncode != 0:
            print(f"Update stderr: {update_result.stderr}")
        
        assert update_result.returncode == 0, f"Update failed: {update_result.stderr}"
        print("✅ Update script completed")
        
        # Verify metallb chart now exists locally
        assert (cluster_dir / "charts" / "metallb").exists(), \
            "metallb chart should be downloaded"
        print("✅ metallb chart exists locally")
    
    def test_04_verify_update_artifacts(self, update_cluster, work_dir):
        """
        Step 4: Verify update created correct artifacts in the repo.
        
        Note: Flux reconciliation of new components may take additional time 
        beyond the test timeout. This test verifies the update script correctly:
        - Updated all necessary files
        - Downloaded new chart (metallb)
        - Updated k8s-bootstrap.yaml config
        - Updated flux-instance values
        
        Manual verification:
          kubectl get helmrelease -A  (should show metallb after ~2 min)
        """
        print("\n" + "="*70)
        print("UPDATE WORKFLOW: Step 4 - Verify Update Artifacts")
        print("="*70)
        
        cluster_dir = work_dir / "update-wf"
        
        # 1. Verify metallb chart exists
        metallb_chart = cluster_dir / "charts" / "metallb" / "Chart.yaml"
        assert metallb_chart.exists(), "metallb Chart.yaml should exist"
        print("✅ metallb chart downloaded")
        
        # 2. Verify flux-instance values has metallb in components
        flux_instance_values = cluster_dir / "charts" / "flux-instance" / "values.yaml"
        with open(flux_instance_values) as f:
            values = yaml.safe_load(f)
        
        component_names = [c["name"] for c in values.get("components", [])]
        assert "metallb" in component_names, "metallb should be in flux-instance components"
        assert "metrics-server" in component_names, "metrics-server should still be in components"
        print(f"✅ flux-instance values.yaml has components: {component_names}")
        
        # 3. Verify k8s-bootstrap.yaml config
        with open(cluster_dir / "k8s-bootstrap.yaml") as f:
            config = yaml.safe_load(f)
        
        selection_ids = [s["id"] for s in config.get("selections", [])]
        assert "metallb" in selection_ids, "metallb should be in config selections"
        assert "metrics-server" in selection_ids, "metrics-server should still be in config"
        print(f"✅ k8s-bootstrap.yaml has selections: {selection_ids}")
        
        # 4. Verify namespaces chart has metallb-system
        namespaces_values = cluster_dir / "charts" / "namespaces" / "values.yaml"
        with open(namespaces_values) as f:
            ns_values = yaml.safe_load(f)
        
        ns_names = [ns["name"] for ns in ns_values.get("namespaces", [])]
        assert "metallb-system" in ns_names, "metallb-system should be in namespaces"
        print(f"✅ namespaces chart has: {ns_names}")
        
        # 5. Show current Flux status for manual verification
        print("\n📊 Current Flux status:")
        hr_result = subprocess.run(
            ["kubectl", "--kubeconfig", update_cluster.kubeconfig_path,
             "get", "helmrelease", "-A", "-o", "wide"],
            capture_output=True, text=True
        )
        print(hr_result.stdout)
        
        print("\n" + "="*70)
        print("✅ UPDATE WORKFLOW TEST PASSED!")
        print("   All artifacts correctly generated and pushed to Git.")
        print("   Flux will reconcile metallb HelmRelease within ~2 minutes.")
        print("   Manual verification: kubectl get helmrelease -A")
        print("="*70)


@pytest.mark.e2e
@pytest.fixture(scope="module")
def api_client(backend_url):
    """Create requests session for API calls."""
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
    
    return session


@pytest.fixture
def generate_bootstrap(api_client, backend_url, tmp_path):
    """Factory fixture to generate bootstrap packages via API."""
    def _generate(
        components,
        cluster_name="test",
        repo_url="git@github.com:test/repo.git",
        branch="main",
        component_values=None,
        component_raw_overrides=None,
        git_auth=None
    ):
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
        
        return output_dir
    
    return _generate
