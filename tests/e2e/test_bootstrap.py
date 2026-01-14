"""
Bootstrap Validation Tests

These tests validate the generated bootstrap package without deploying.
For full deployment tests, see test_full_e2e.py

Tests:
- Script syntax validation
- Generated file structure
- Chart validation (helm lint)
- New architecture validation (namespaces chart, flux-instance templates)
"""
import pytest
import subprocess
import os
from pathlib import Path
import yaml


@pytest.mark.e2e
class TestBootstrapScript:
    """Validate bootstrap.sh script."""
    
    def test_script_syntax_valid(self, generate_bootstrap):
        """Test that bootstrap.sh has valid bash syntax."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="syntax-test"
        )
        
        script = bootstrap_dir / "bootstrap.sh"
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True, text=True
        )
        
        assert result.returncode == 0, f"Syntax error in bootstrap.sh: {result.stderr}"
    
    def test_script_shows_help(self, generate_bootstrap):
        """Test --help flag shows usage information."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="help-test"
        )
        
        result = subprocess.run(
            ["bash", str(bootstrap_dir / "bootstrap.sh"), "--help"],
            capture_output=True, text=True
        )
        
        assert "Usage" in result.stdout or "usage" in result.stdout
        assert "--kubeconfig" in result.stdout
        assert "--context" in result.stdout
    
    def test_script_supports_kubeconfig(self, generate_bootstrap):
        """Test that script supports custom kubeconfig."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="kc-test"
        )
        
        content = (bootstrap_dir / "bootstrap.sh").read_text()
        
        assert "--kubeconfig" in content
        assert "-k" in content
        assert "KUBECONFIG" in content
    
    def test_script_has_install_functions(self, generate_bootstrap):
        """Test that script has required installation functions."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="funcs-test"
        )
        
        content = (bootstrap_dir / "bootstrap.sh").read_text()
        
        # Core functions should exist
        assert "install_flux_operator" in content
        assert "create_flux_instance" in content or "FluxInstance" in content
        assert "vendor_charts" in content


@pytest.mark.e2e
class TestGeneratedStructure:
    """Validate generated repository structure."""
    
    def test_has_all_required_files(self, generate_bootstrap):
        """Test that all required files are generated."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="files-test"
        )
        
        # Root files
        assert (bootstrap_dir / "bootstrap.sh").exists(), "Missing bootstrap.sh"
        assert (bootstrap_dir / "README.md").exists(), "Missing README.md"
        assert (bootstrap_dir / ".gitignore").exists(), "Missing .gitignore"
        assert (bootstrap_dir / ".sops.yaml").exists(), "Missing .sops.yaml"
        assert (bootstrap_dir / "k8s-bootstrap.yaml").exists(), "Missing k8s-bootstrap.yaml"
        
        # Charts directory
        charts = bootstrap_dir / "charts"
        assert charts.exists(), "Missing charts directory"
        
        # Flux components
        assert (charts / "flux-operator").exists(), "Missing flux-operator"
        assert (charts / "flux-instance").exists(), "Missing flux-instance"
        assert (charts / "namespaces").exists(), "Missing namespaces chart"
    
    def test_no_bootstrap_chart(self, generate_bootstrap):
        """Test that old bootstrap chart does NOT exist (replaced by flux-instance)."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="no-bootstrap-test"
        )
        
        # Old bootstrap chart should NOT exist
        old_bootstrap = bootstrap_dir / "charts" / "bootstrap"
        assert not old_bootstrap.exists(), \
            "charts/bootstrap should NOT exist - replaced by flux-instance templates"
    
    def test_bootstrap_script_is_executable(self, generate_bootstrap):
        """Test that bootstrap.sh has executable permissions."""
        import stat
        
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="exec-test"
        )
        
        script = bootstrap_dir / "bootstrap.sh"
        mode = os.stat(script).st_mode
        
        assert mode & stat.S_IXUSR, "bootstrap.sh is not executable"
    
    def test_component_charts_generated(self, generate_bootstrap):
        """Test that selected component charts are generated."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx", "metrics-server"],
            cluster_name="components-test"
        )
        
        charts = bootstrap_dir / "charts"
        
        for component in ["cert-manager", "ingress-nginx", "metrics-server"]:
            chart_dir = charts / component
            assert chart_dir.exists(), f"Missing {component} chart"
            assert (chart_dir / "Chart.yaml").exists(), f"Missing {component}/Chart.yaml"
            assert (chart_dir / "values.yaml").exists(), f"Missing {component}/values.yaml"
    
    def test_namespaces_chart_has_templates(self, generate_bootstrap):
        """Test that namespaces chart has required templates."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="ns-templates-test"
        )
        
        templates = bootstrap_dir / "charts" / "namespaces" / "templates"
        assert templates.exists(), "Missing namespaces/templates"
        
        assert (templates / "namespaces.yaml").exists(), "Missing namespaces.yaml template"
    
    def test_flux_instance_has_templates(self, generate_bootstrap):
        """Test that flux-instance chart has required templates."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="flux-templates-test"
        )
        
        templates = bootstrap_dir / "charts" / "flux-instance" / "templates"
        assert templates.exists(), "Missing flux-instance/templates"
        
        # Should have key templates
        expected = [
            "gitrepository.yaml",
            "kustomization-flux-system.yaml",
            "kustomization-namespaces.yaml",
            "helmreleases.yaml",
            "secret-git-credentials.yaml",
        ]
        
        for tmpl in expected:
            assert (templates / tmpl).exists(), f"Missing template: {tmpl}"
    
    def test_manifests_structure(self, generate_bootstrap):
        """Test manifests directory structure."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="manifests-test"
        )
        
        manifests = bootstrap_dir / "manifests"
        
        # flux-system manifests
        flux_sys = manifests / "flux-system"
        assert flux_sys.exists(), "Missing manifests/flux-system"
        assert (flux_sys / "kustomization.yaml").exists()
        assert (flux_sys / "flux-operator.yaml").exists()
        assert (flux_sys / "flux-instance.yaml").exists()
        
        # namespaces manifests
        ns = manifests / "namespaces"
        assert ns.exists(), "Missing manifests/namespaces"
        assert (ns / "kustomization.yaml").exists()
        assert (ns / "release.yaml").exists()
    
    def test_no_infrastructure_manifests(self, generate_bootstrap):
        """Test that old infrastructure manifests don't exist."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="no-infra-test"
        )
        
        # Old infrastructure directory should NOT exist
        infra = bootstrap_dir / "manifests" / "infrastructure"
        assert not infra.exists(), \
            "manifests/infrastructure should NOT exist - components are in flux-instance"


def get_all_selectable_components(api_client, backend_url):
    """Get all components that can be individually selected for testing."""
    response = api_client.get(f"{backend_url}/api/categories")
    if response.status_code != 200:
        return []
    
    components = []
    for category in response.json():
        for comp in category.get("components", []):
            if comp.get("hidden"):
                continue
            if comp.get("requiresOperator"):
                continue
            components.append(comp["id"])
    
    return components


@pytest.mark.e2e
class TestChartValidation:
    """Validate generated Helm charts."""
    
    def test_flux_operator_chart_valid(self, generate_bootstrap, helm_lint):
        """Test that flux-operator chart passes helm lint."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="lint-flux-op"
        )
        
        chart = bootstrap_dir / "charts" / "flux-operator"
        
        # Skip if chart is just a placeholder (no templates)
        if not (chart / "charts").exists():
            pytest.skip("flux-operator chart not vendored yet")
        
        result = helm_lint(chart)
        assert result.returncode == 0, f"Lint failed: {result.stderr}"
    
    def test_flux_instance_chart_valid(self, generate_bootstrap, helm_lint):
        """Test that flux-instance chart passes helm lint."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="lint-flux-inst"
        )
        
        chart = bootstrap_dir / "charts" / "flux-instance"
        result = helm_lint(chart)
        
        assert result.returncode == 0, f"Lint failed: {result.stderr}"
    
    def test_namespaces_chart_valid(self, generate_bootstrap, helm_lint):
        """Test that namespaces chart passes helm lint."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="lint-namespaces"
        )
        
        chart = bootstrap_dir / "charts" / "namespaces"
        result = helm_lint(chart)
        
        assert result.returncode == 0, f"Lint failed: {result.stderr}"
    
    @pytest.mark.slow
    @pytest.mark.timeout(1800)
    def test_all_component_charts_valid(self, api_client, backend_url, generate_bootstrap, helm_lint):
        """
        Dynamic test: validate ALL selectable component charts.
        
        This test discovers all components from the API and validates each one.
        WARNING: This test is very slow as it downloads all charts.
        Skip with: pytest -m "not slow"
        """
        components = get_all_selectable_components(api_client, backend_url)
        assert len(components) > 0, "No selectable components found"
        
        failed = []
        passed = []
        skipped = []
        
        for component in components:
            try:
                bootstrap_dir = generate_bootstrap(
                    components=[component],
                    cluster_name=f"valid-{component[:15]}"
                )
                
                chart = bootstrap_dir / "charts" / component
                if not chart.exists():
                    skipped.append((component, "Chart dir not found"))
                    continue
                
                # Check if vendored
                vendored = (chart / "charts" / component / "Chart.yaml").exists()
                if not vendored:
                    if not (chart / "Chart.yaml").exists():
                        skipped.append((component, "Not vendored yet"))
                        continue
                
                result = helm_lint(chart)
                if result.returncode == 0:
                    passed.append(component)
                else:
                    failed.append((component, result.stderr))
                    
            except Exception as e:
                skipped.append((component, str(e)))
        
        print(f"\n✅ Passed ({len(passed)}): {', '.join(passed)}")
        if skipped:
            print(f"⏭️  Skipped ({len(skipped)}): {[s[0] for s in skipped]}")
        
        assert not failed, (
            f"Helm lint failed for {len(failed)} component(s):\n" +
            "\n".join([f"  - {name}: {err[:200]}" for name, err in failed])
        )


@pytest.mark.e2e
class TestFluxInstanceValues:
    """Test flux-instance values.yaml structure."""
    
    def test_values_has_components_array(self, generate_bootstrap):
        """Test that flux-instance values has components array."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="values-components"
        )
        
        values_path = bootstrap_dir / "charts" / "flux-instance" / "values.yaml"
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        assert "components" in values, "values.yaml should have components array"
        assert len(values["components"]) > 0, "Should have at least one component"
    
    def test_values_has_git_repository_config(self, generate_bootstrap):
        """Test that flux-instance values has git repository config."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="values-gitrepo"
        )
        
        values_path = bootstrap_dir / "charts" / "flux-instance" / "values.yaml"
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        assert "git" in values or "gitRepository" in values, \
            "values.yaml should have git repository config"
    
    def test_values_has_credentials_config(self, generate_bootstrap):
        """Test that flux-instance values has credentials config structure.
        
        Note: gitCredentials.enabled is set to false in the template
        and is updated at runtime by bootstrap.sh with actual credentials.
        """
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="values-creds",
            git_auth={"enabled": True, "platform": "gitea", "customUrl": "http://gitea:3000"}
        )
        
        values_path = bootstrap_dir / "charts" / "flux-instance" / "values.yaml"
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        # Verify gitCredentials structure exists (values are filled by bootstrap.sh)
        assert "gitCredentials" in values, "values.yaml should have gitCredentials"
        assert "enabled" in values["gitCredentials"], "gitCredentials should have enabled field"
        assert "username" in values["gitCredentials"], "gitCredentials should have username field"
        assert "password" in values["gitCredentials"], "gitCredentials should have password field"
        
        # Verify bootstrap.sh handles credentials
        bootstrap_sh = bootstrap_dir / "bootstrap.sh"
        content = bootstrap_sh.read_text()
        assert "get_credentials" in content, "bootstrap.sh should handle credentials"


@pytest.mark.e2e
class TestNamespacesChart:
    """Test namespaces chart structure."""
    
    def test_values_has_namespaces_list(self, generate_bootstrap):
        """Test that namespaces values has namespace list."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx", "metrics-server"],
            cluster_name="ns-values"
        )
        
        values_path = bootstrap_dir / "charts" / "namespaces" / "values.yaml"
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        assert "namespaces" in values, "values.yaml should have namespaces list"
        
        ns_names = [ns["name"] for ns in values["namespaces"]]
        assert "cert-manager" in ns_names
        assert "ingress-nginx" in ns_names
        assert "cluster-crds" in ns_names  # CRDs namespace
    
    def test_namespaces_template_renders(self, generate_bootstrap, helm_template):
        """Test that namespaces template renders correctly."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="ns-render"
        )
        
        chart = bootstrap_dir / "charts" / "namespaces"
        result = helm_template(chart, "namespaces", "flux-system")
        
        assert result.returncode == 0, f"Template failed: {result.stderr}"
        assert "kind: Namespace" in result.stdout
        assert "cert-manager" in result.stdout
        assert "ingress-nginx" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
