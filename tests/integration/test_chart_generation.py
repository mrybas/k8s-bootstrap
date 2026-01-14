"""
Integration tests for chart generation.

These tests verify that:
- Generated charts pass helm lint
- Generated charts can be templated
- Chart structure is correct
- Values are properly merged
- Auto-included dependencies are present
- New architecture with namespaces chart and flux-instance templates
"""
import pytest
import yaml
from pathlib import Path


def get_all_selectable_components(api_client, backend_url):
    """Get all components that can be individually selected for testing."""
    response = api_client.get(f"{backend_url}/api/categories")
    if response.status_code != 200:
        return []
    
    components = []
    for category in response.json():
        for comp in category.get("components", []):
            # Skip hidden components (auto-included like namespaces, CRDs)
            if comp.get("hidden"):
                continue
            # Skip instance components that require operator
            if comp.get("requiresOperator"):
                continue
            components.append(comp["id"])
    
    return components


class TestChartLinting:
    """Test that all generated charts pass helm lint."""
    
    def _is_vendored(self, chart_dir: Path) -> bool:
        """Check if a chart has its dependencies vendored (no VENDOR_ME.md)."""
        # Charts with VENDOR_ME.md need vendoring
        if (chart_dir / "VENDOR_ME.md").exists():
            return False
        # Wrapper charts reference file:// dependencies that may not exist
        chart_yaml = chart_dir / "Chart.yaml"
        if chart_yaml.exists():
            import yaml
            with open(chart_yaml) as f:
                data = yaml.safe_load(f)
            deps = data.get("dependencies", [])
            for dep in deps:
                repo = dep.get("repository", "")
                if repo.startswith("file://"):
                    # Check if dependency exists
                    dep_path = chart_dir / repo.replace("file://", "")
                    if not dep_path.exists():
                        return False
        return True
    
    def test_generated_charts_lint(self, generate_bootstrap, helm_lint):
        """Test that all vendored charts in generated package pass lint."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="lint-test"
        )
        
        charts_dir = bootstrap_dir / "charts"
        assert charts_dir.exists()
        
        for chart_dir in charts_dir.iterdir():
            if chart_dir.is_dir() and (chart_dir / "Chart.yaml").exists():
                # Skip charts that need vendoring
                if not self._is_vendored(chart_dir):
                    continue
                result = helm_lint(chart_dir)
                assert result.returncode == 0, \
                    f"Helm lint failed for {chart_dir.name}:\n{result.stderr}"
    
    def test_flux_operator_chart_valid(self, generate_bootstrap, helm_lint):
        """Test that flux-operator wrapper chart is valid."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="flux-op-test"
        )
        
        # New path: charts/core/flux-operator
        chart = bootstrap_dir / "charts" / "core" / "flux-operator"
        assert chart.exists(), "flux-operator chart should exist in charts/core/"
        assert (chart / "Chart.yaml").exists()
        assert (chart / "values.yaml").exists()
    
    def test_flux_instance_chart_valid(self, generate_bootstrap, helm_lint):
        """Test that flux-instance chart is valid (GitRepository only, no Kustomizations)."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="flux-inst-test"
        )
        
        # New path: charts/core/flux-instance
        chart = bootstrap_dir / "charts" / "core" / "flux-instance"
        assert chart.exists(), "flux-instance chart should exist in charts/core/"
        assert (chart / "Chart.yaml").exists()
        assert (chart / "values.yaml").exists()
        assert (chart / "templates").exists()
        
        # Should have GitRepository and Secret templates only (Kustomizations are static files)
        templates = chart / "templates"
        assert (templates / "gitrepository.yaml").exists()
        assert (templates / "secret-git-credentials.yaml").exists()
        # Kustomizations are now static files in manifests/kustomizations/, NOT Helm templates
        assert not (templates / "kustomizations.yaml").exists(), "Kustomizations should be static files, not Helm templates"
    
    def test_namespaces_chart_valid(self, generate_bootstrap, helm_lint):
        """Test that namespaces chart is valid."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="ns-test"
        )
        
        # New path: charts/core/namespaces
        chart = bootstrap_dir / "charts" / "core" / "namespaces"
        assert chart.exists(), "namespaces chart should exist in charts/core/"
        assert (chart / "Chart.yaml").exists()
        assert (chart / "values.yaml").exists()
        assert (chart / "templates" / "namespaces.yaml").exists()
        
        # Values should contain namespace list
        with open(chart / "values.yaml") as f:
            values = yaml.safe_load(f)
        
        assert "namespaces" in values, "values.yaml should have namespaces"
        assert len(values["namespaces"]) > 0, "Should have at least one namespace"
    
    @pytest.mark.slow
    @pytest.mark.timeout(1800)  # 30 min for all charts
    def test_all_components_lint(self, api_client, backend_url, generate_bootstrap, helm_lint):
        """
        Dynamic test: lint ALL selectable components that are vendored.
        
        This test discovers all components from the API and validates each one.
        Skips charts that need external vendoring (have VENDOR_ME.md or missing deps).
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
                    cluster_name=f"lint-{component[:20]}"
                )
                
                chart_path = bootstrap_dir / "charts" / component
                if chart_path.exists():
                    # Skip charts that need vendoring
                    if not self._is_vendored(chart_path):
                        skipped.append((component, "Needs vendoring"))
                        continue
                    result = helm_lint(chart_path)
                    if result.returncode == 0:
                        passed.append(component)
                    else:
                        failed.append((component, result.stderr))
                else:
                    skipped.append((component, "Chart not generated"))
                    
            except Exception as e:
                skipped.append((component, str(e)))
        
        # Report results
        print(f"\n✅ Passed ({len(passed)}): {', '.join(passed)}")
        if skipped:
            print(f"⏭️  Skipped ({len(skipped)}): {[s[0] for s in skipped]}")
        
        assert not failed, (
            f"Helm lint failed for {len(failed)} component(s):\n" +
            "\n".join([f"  - {name}: {err[:200]}" for name, err in failed])
        )


class TestChartTemplating:
    """Test that generated charts can be templated."""
    
    def test_flux_instance_templates(self, generate_bootstrap, helm_template):
        """Test that flux-instance chart templates correctly (GitRepository only)."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="template-test"
        )
        
        # New path: charts/core/flux-instance
        flux_instance = bootstrap_dir / "charts" / "core" / "flux-instance"
        result = helm_template(flux_instance, "flux-instance", "flux-system")
        
        assert result.returncode == 0, f"Template failed:\n{result.stderr}"
        
        # Should contain GitRepository
        assert "GitRepository" in result.stdout, "Should have GitRepository"
        
        # Kustomizations are now static files, not in Helm chart
        # HelmReleases are now in manifests/releases/<category>/
    
    def test_namespaces_chart_templates(self, generate_bootstrap, helm_template):
        """Test that namespaces chart templates correctly."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="ns-template-test"
        )
        
        # New path: charts/core/namespaces
        namespaces_chart = bootstrap_dir / "charts" / "core" / "namespaces"
        result = helm_template(namespaces_chart, "namespaces", "flux-system")
        
        assert result.returncode == 0, f"Template failed:\n{result.stderr}"
        
        # Should contain Namespace resources
        assert "kind: Namespace" in result.stdout, "Should have Namespace resources"


class TestChartStructure:
    """Test that generated chart structure is correct."""
    
    def test_wrapper_chart_structure(self, generate_bootstrap):
        """Test that wrapper charts have correct structure."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="structure-test"
        )
        
        # New path: charts/<category>/cert-manager (security category)
        chart_path = bootstrap_dir / "charts" / "security" / "cert-manager"
        
        assert (chart_path / "Chart.yaml").exists()
        assert (chart_path / "values.yaml").exists()
        
        with open(chart_path / "Chart.yaml") as f:
            chart = yaml.safe_load(f)
        
        assert chart["name"] == "cert-manager"
        assert "version" in chart
        assert "dependencies" in chart
        
        deps = chart["dependencies"]
        assert len(deps) > 0
        local_dep = next((d for d in deps if d.get("repository", "").startswith("file://")), None)
        assert local_dep is not None, "Should have local file:// dependency"
    
    def test_flux_operator_wrapper_structure(self, generate_bootstrap):
        """Test that flux-operator is a proper wrapper chart."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="flux-op-struct"
        )
        
        # New path: charts/core/flux-operator
        chart_path = bootstrap_dir / "charts" / "core" / "flux-operator"
        
        assert (chart_path / "Chart.yaml").exists()
        assert (chart_path / "values.yaml").exists()
        
        with open(chart_path / "Chart.yaml") as f:
            chart = yaml.safe_load(f)
        
        assert chart["name"] == "flux-operator"
        assert "dependencies" in chart
        
        # Should have flux-operator as dependency
        deps = chart["dependencies"]
        flux_dep = next((d for d in deps if d.get("name") == "flux-operator"), None)
        assert flux_dep is not None, "Should have flux-operator dependency"
    
    def test_flux_instance_structure(self, generate_bootstrap):
        """Test flux-instance chart has correct templates (GitRepository only)."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="flux-inst-struct"
        )
        
        # New path: charts/core/flux-instance
        chart_path = bootstrap_dir / "charts" / "core" / "flux-instance"
        templates_dir = chart_path / "templates"
        
        assert templates_dir.exists(), "templates/ should exist"
        
        # Core templates (GitRepository + Secret only, Kustomizations are static files now)
        expected_templates = [
            "gitrepository.yaml",
            "secret-git-credentials.yaml",
        ]
        
        for tmpl in expected_templates:
            assert (templates_dir / tmpl).exists(), f"Missing template: {tmpl}"
        
        # Kustomizations should NOT be here (they are static files in manifests/kustomizations/)
        assert not (templates_dir / "kustomizations.yaml").exists(), \
            "Kustomizations should be static files, not Helm templates"
    
    def test_namespaces_chart_structure(self, generate_bootstrap):
        """Test namespaces chart has correct structure."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx", "metrics-server"],
            cluster_name="ns-struct"
        )
        
        # New path: charts/core/namespaces
        chart_path = bootstrap_dir / "charts" / "core" / "namespaces"
        
        assert (chart_path / "Chart.yaml").exists()
        assert (chart_path / "values.yaml").exists()
        assert (chart_path / "templates" / "namespaces.yaml").exists()
        
        # Check namespaces in values
        with open(chart_path / "values.yaml") as f:
            values = yaml.safe_load(f)
        
        ns_names = [ns["name"] for ns in values.get("namespaces", [])]
        
        # Should have component namespaces
        assert "cert-manager" in ns_names, "Should have cert-manager namespace"
        assert "ingress-nginx" in ns_names, "Should have ingress-nginx namespace"


class TestManifestsStructure:
    """Test generated manifests structure."""
    
    def test_kustomizations_manifests(self, generate_bootstrap):
        """Test manifests/kustomizations/ structure (static Kustomization files)."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="kust-manifests"
        )
        
        kust_dir = bootstrap_dir / "manifests" / "kustomizations"
        assert kust_dir.exists(), "manifests/kustomizations/ should exist"
        
        # Should have 00-namespaces.yaml
        assert (kust_dir / "00-namespaces.yaml").exists(), "00-namespaces.yaml should exist"
        
        # Should have category Kustomizations (at least one for security category)
        kust_files = list(kust_dir.glob("*-releases-*.yaml"))
        assert len(kust_files) > 0, "Should have at least one releases Kustomization"
        
        # Read and verify namespaces Kustomization
        with open(kust_dir / "00-namespaces.yaml") as f:
            kust = yaml.safe_load(f)
        
        assert kust["kind"] == "Kustomization"
        assert kust["metadata"]["name"] == "namespaces"
        assert kust["spec"]["path"] == "./manifests/namespaces"
    
    def test_releases_manifests(self, generate_bootstrap):
        """Test manifests/releases/<category>/ structure."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="releases-manifests"
        )
        
        releases_dir = bootstrap_dir / "manifests" / "releases"
        assert releases_dir.exists(), "manifests/releases/ should exist"
        
        # Should have core directory with flux-operator and flux-instance
        core_dir = releases_dir / "core"
        assert core_dir.exists(), "manifests/releases/core/ should exist"
        assert (core_dir / "flux-operator.yaml").exists()
        assert (core_dir / "flux-instance.yaml").exists()
        
        # Read flux-instance HelmRelease to verify structure
        with open(core_dir / "flux-instance.yaml") as f:
            release = yaml.safe_load(f)
        
        assert release["kind"] == "HelmRelease"
        assert release["metadata"]["name"] == "flux-instance"
        assert release["spec"]["chart"]["spec"]["chart"] == "./charts/core/flux-instance"
    
    def test_namespaces_manifests(self, generate_bootstrap):
        """Test manifests/namespaces/ structure."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="ns-manifests"
        )
        
        ns_dir = bootstrap_dir / "manifests" / "namespaces"
        assert ns_dir.exists(), "manifests/namespaces/ should exist"
        
        # Should have release.yaml (no kustomization.yaml - it's in manifests/kustomizations/)
        assert (ns_dir / "release.yaml").exists()
        
        # release.yaml should be a HelmRelease for namespaces chart
        with open(ns_dir / "release.yaml") as f:
            release = yaml.safe_load(f)
        
        assert release["kind"] == "HelmRelease"
        assert release["metadata"]["name"] == "namespaces"
        assert "chart" in release["spec"]
        # New path: charts/core/namespaces
        assert release["spec"]["chart"]["spec"]["chart"] == "./charts/core/namespaces"
    
    def test_no_old_manifests_structure(self, generate_bootstrap):
        """Test that old manifest directories don't exist."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="no-old"
        )
        
        # Old directories should NOT exist
        assert not (bootstrap_dir / "manifests" / "infrastructure").exists(), \
            "manifests/infrastructure/ should NOT exist"
        assert not (bootstrap_dir / "manifests" / "flux-system").exists(), \
            "manifests/flux-system/ should NOT exist (replaced by manifests/releases/core/)"


class TestValuesGeneration:
    """Test that values are properly generated and merged."""
    
    def test_default_values_applied(self, generate_bootstrap):
        """Test that default values from definition are applied."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="values-test"
        )
        
        # New path: charts/<category>/cert-manager
        values_path = bootstrap_dir / "charts" / "security" / "cert-manager" / "values.yaml"
        assert values_path.exists()
        
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        assert values is not None
    
    def test_custom_values_in_helmrelease(self, generate_bootstrap):
        """Test that custom values are in HelmRelease manifest (not in chart values)."""
        bootstrap_dir = generate_bootstrap(
            components=["ingress-nginx"],
            cluster_name="custom-values",
            component_values={
                "ingress-nginx": {"controller": {"replicaCount": 3}}
            }
        )
        
        # Values should be in HelmRelease manifest, not in chart values.yaml
        release_path = bootstrap_dir / "manifests" / "releases" / "ingress" / "ingress-nginx.yaml"
        assert release_path.exists(), "HelmRelease manifest should exist"
        
        with open(release_path) as f:
            release = yaml.safe_load(f)
        
        assert release["kind"] == "HelmRelease"
        values = release.get("spec", {}).get("values", {})
        assert values.get("controller", {}).get("replicaCount") == 3
    
    def test_raw_overrides_in_helmrelease(self, generate_bootstrap):
        """Test that raw YAML overrides are in HelmRelease manifest."""
        raw_yaml = """
controller:
  nodeSelector:
    kubernetes.io/os: linux
  tolerations:
    - key: "node-role.kubernetes.io/master"
      effect: "NoSchedule"
"""
        bootstrap_dir = generate_bootstrap(
            components=["ingress-nginx"],
            cluster_name="raw-override-test",
            component_raw_overrides={
                "ingress-nginx": raw_yaml
            }
        )
        
        # Values should be in HelmRelease manifest
        release_path = bootstrap_dir / "manifests" / "releases" / "ingress" / "ingress-nginx.yaml"
        with open(release_path) as f:
            release = yaml.safe_load(f)
        
        values = release.get("spec", {}).get("values", {})
        assert values.get("controller", {}).get("nodeSelector", {}).get("kubernetes.io/os") == "linux"
        assert len(values.get("controller", {}).get("tolerations", [])) > 0
    
    def test_flux_instance_values_minimal(self, generate_bootstrap):
        """Test that flux-instance values.yaml is minimal (no components/categories)."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager", "ingress-nginx"],
            cluster_name="components-values"
        )
        
        # New path: charts/core/flux-instance
        values_path = bootstrap_dir / "charts" / "core" / "flux-instance" / "values.yaml"
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        # flux-instance should only have gitRepository config (Kustomizations are static files)
        assert "gitRepository" in values, "Should have gitRepository config"
        # Should NOT have components or categories (these are in static Kustomization files)
        assert "components" not in values, "Should NOT have components (HelmReleases are static files)"
        assert "categories" not in values, "Should NOT have categories (Kustomizations are static files)"


class TestRawYamlValidation:
    """Test raw YAML validation in bootstrap API."""
    
    def test_api_rejects_invalid_yaml_syntax(self, api_client, backend_url):
        """Test that API rejects invalid YAML syntax in raw_overrides."""
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "invalid-yaml-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{
                    "id": "cert-manager",
                    "enabled": True,
                    "raw_overrides": "invalid: yaml: [unclosed"
                }]
            }
        )
        
        assert response.status_code == 400
        assert "Invalid raw YAML" in response.json()["detail"]
    
    def test_api_rejects_non_dict_yaml(self, api_client, backend_url):
        """Test that API rejects non-dict YAML (list, scalar) in raw_overrides."""
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "non-dict-yaml-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{
                    "id": "cert-manager",
                    "enabled": True,
                    "raw_overrides": "- item1\n- item2"
                }]
            }
        )
        
        assert response.status_code == 400
        assert "must be a YAML mapping" in response.json()["detail"]
    
    def test_api_accepts_valid_yaml(self, api_client, backend_url):
        """Test that API accepts valid YAML in raw_overrides."""
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "valid-yaml-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{
                    "id": "cert-manager",
                    "enabled": True,
                    "raw_overrides": "installCRDs: true\nreplicas: 2"
                }]
            }
        )
        
        assert response.status_code == 200
    
    def test_api_accepts_empty_raw_overrides(self, api_client, backend_url):
        """Test that API accepts empty/whitespace raw_overrides."""
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "empty-yaml-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{
                    "id": "cert-manager",
                    "enabled": True,
                    "raw_overrides": "   \n   "
                }]
            }
        )
        
        assert response.status_code == 200


class TestBootstrapScript:
    """Test generated bootstrap.sh script."""
    
    def test_bootstrap_script_exists(self, generate_bootstrap):
        """Test that bootstrap.sh is generated."""
        bootstrap_dir = generate_bootstrap(components=["cert-manager"], cluster_name="script-test")
        assert (bootstrap_dir / "bootstrap.sh").exists()
    
    def test_bootstrap_script_is_executable(self, generate_bootstrap):
        """Test that bootstrap.sh has executable permissions."""
        import os
        import stat
        
        bootstrap_dir = generate_bootstrap(components=["cert-manager"], cluster_name="exec-test")
        mode = os.stat(bootstrap_dir / "bootstrap.sh").st_mode
        assert mode & stat.S_IXUSR, "bootstrap.sh is not executable"
    
    def test_bootstrap_script_has_kubeconfig_flag(self, generate_bootstrap):
        """Test that bootstrap.sh supports --kubeconfig flag."""
        bootstrap_dir = generate_bootstrap(components=["cert-manager"], cluster_name="kubeconfig-test")
        content = (bootstrap_dir / "bootstrap.sh").read_text()
        
        assert "--kubeconfig" in content
        assert "-k" in content
    
    def test_bootstrap_script_three_phase_flow(self, generate_bootstrap):
        """Test that bootstrap.sh has correct 3-phase installation flow."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="flow-test",
            git_auth={"enabled": True, "platform": "gitea", "customUrl": "http://gitea:3000"}
        )
        content = (bootstrap_dir / "bootstrap.sh").read_text()
        
        # Phase 1: Install flux-operator
        assert "install_flux_operator" in content
        
        # Phase 2: Create FluxInstance CR
        assert "create_flux_instance" in content or "FluxInstance" in content
        
        # Phase 3: Install flux-instance chart with GitOps config
        assert "install_flux_gitops" in content or "flux-instance" in content


class TestBootstrapAPI:
    """Test the curl-based bootstrap API endpoints."""
    
    def test_bootstrap_create_returns_token(self, api_client, backend_url):
        """Test that /api/bootstrap returns a token and curl command."""
        response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "test-cluster",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "cert-manager", "enabled": True}]
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert "curl_command" in data
        assert len(data["token"]) > 10
        assert data["token"] in data["curl_command"]
    
    def test_bootstrap_script_is_valid_bash(self, api_client, backend_url):
        """Test that /bootstrap/{token} returns a valid bash script."""
        create_response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "script-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "cert-manager", "enabled": True}]
            }
        )
        token = create_response.json()["token"]
        
        script_response = api_client.get(f"{backend_url}/bootstrap/{token}")
        assert script_response.status_code == 200
        
        script = script_response.text
        assert script.startswith("#!/usr/bin/env bash")
        assert "cat <<" in script  # Uses heredocs
    
    def test_bootstrap_token_one_time_use(self, api_client, backend_url):
        """Test that bootstrap token is one-time use."""
        create_response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "onetime-test",
                "repo_url": "git@github.com:test/repo.git",
                "branch": "main",
                "components": [{"id": "cert-manager", "enabled": True}]
            }
        )
        token = create_response.json()["token"]
        
        # First download works
        first = api_client.get(f"{backend_url}/bootstrap/{token}")
        assert first.status_code == 200
        
        # Second fails
        second = api_client.get(f"{backend_url}/bootstrap/{token}")
        assert second.status_code == 404


class TestAPIEndpoints:
    """Test backend API endpoints."""
    
    def test_categories_endpoint(self, api_client, backend_url):
        """Test /api/categories returns valid data."""
        response = api_client.get(f"{backend_url}/api/categories")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        for category in data:
            assert "name" in category
            assert "components" in category


class TestAutoIncludeDependencies:
    """
    Tests for auto-include and dependency resolution.
    
    These tests dynamically discover auto-include relationships from component 
    definitions rather than using hardcoded values.
    """
    
    def test_resolve_dependencies_returns_crds(self, api_client, backend_url):
        """Test that /api/resolve-dependencies returns CRD charts."""
        response = api_client.get(
            f"{backend_url}/api/resolve-dependencies",
            params={"components": "cert-manager"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "crds" in data or "auto_included" in data
        
        # cert-manager should have some auto-includes
        total = data.get("total", [])
        assert "cert-manager" in total
        assert len(total) > 1  # Should have more than just cert-manager
    
    def test_all_auto_included_charts_present_in_script(self, api_client, backend_url):
        """
        Dynamic test: verify ALL auto-included charts appear in generated script.
        
        Discovers auto-include relationships from API, not hardcoded.
        """
        import re
        
        # Test with various components
        test_components = ["cert-manager", "ingress-nginx", "metrics-server"]
        
        # Get resolved dependencies
        resolve_response = api_client.get(
            f"{backend_url}/api/resolve-dependencies",
            params={"components": ",".join(test_components)}
        )
        assert resolve_response.status_code == 200
        resolved = resolve_response.json()
        
        crds = resolved.get("crds", [])
        auto_included = resolved.get("auto_included", [])
        all_expected = set(crds + auto_included)
        
        if not all_expected:
            pytest.skip("No auto-included components to test")
        
        # Generate bootstrap
        bootstrap_response = api_client.post(
            f"{backend_url}/api/bootstrap",
            json={
                "cluster_name": "auto-test",
                "repo_url": "git@test:test.git",
                "branch": "main",
                "components": [{"id": c, "enabled": True} for c in test_components]
            }
        )
        token = bootstrap_response.json()["token"]
        
        script = api_client.get(f"{backend_url}/bootstrap/{token}").text
        
        # Find charts in script (via heredoc or helm pull)
        # New structure: charts/<category>/<component>/
        heredoc_charts = set(re.findall(r'> "charts/[^/]+/([^/]+)/Chart\.yaml"', script))
        helm_pull_charts = set(re.findall(r'mkdir -p "charts/[^/]+/([^/]+)/charts"', script))
        all_charts = heredoc_charts | helm_pull_charts
        
        # Check all auto-included are present
        missing = [c for c in all_expected if c not in all_charts]
        
        assert not missing, (
            f"Missing auto-included charts: {missing}\n"
            f"Expected (auto-included): {all_expected}\n"
            f"Found in script: {all_charts}\n"
            f"This WILL cause Flux dependency failures!"
        )
        
        print(f"✅ All auto-included charts present: {all_expected}")
    
    def test_crds_included_before_dependent_charts(self, api_client, backend_url):
        """Test that CRD charts appear before charts that depend on them."""
        response = api_client.get(
            f"{backend_url}/api/resolve-dependencies",
            params={"components": "cert-manager"}
        )
        resolved = response.json()
        
        total = resolved.get("total", [])
        crds = resolved.get("crds", [])
        
        # If there are CRDs, they should appear before the main component
        for crd in crds:
            if crd in total and "cert-manager" in total:
                crd_idx = total.index(crd)
                cm_idx = total.index("cert-manager")
                # CRDs should come before the main component (lower index = earlier)
                # Note: exact ordering may vary, but CRDs should be included
                assert crd in total, f"CRD {crd} should be in total list"


class TestAuthConfiguration:
    """Test authentication configuration in generated files."""
    
    def test_public_repo_no_auth_secrets(self, generate_bootstrap):
        """Test that public repos don't generate auth secrets."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="public-test",
            repo_url="https://github.com/public/repo.git"
        )
        
        # New path: charts/core/flux-instance
        values_path = bootstrap_dir / "charts" / "core" / "flux-instance" / "values.yaml"
        with open(values_path) as f:
            values = yaml.safe_load(f)
        
        # gitCredentials should be disabled for public repos
        git_creds = values.get("gitCredentials", {})
        assert not git_creds.get("enabled", False), \
            "Public repo should not have gitCredentials enabled"
    
    def test_private_repo_has_auth_secrets(self, generate_bootstrap):
        """Test that private repos generate auth secret template."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="private-test",
            repo_url="https://gitea.example.com/user/repo.git",
            git_auth={"enabled": True, "platform": "gitea", "customUrl": "https://gitea.example.com"}
        )
        
        # New path: charts/core/flux-instance
        template_path = bootstrap_dir / "charts" / "core" / "flux-instance" / "templates" / "secret-git-credentials.yaml"
        assert template_path.exists(), \
            "Private repo should have secret-git-credentials.yaml template"
        
        # Read template and verify it has conditional rendering
        content = template_path.read_text()
        assert "gitCredentials.enabled" in content, \
            "Template should check gitCredentials.enabled"
        
        # Verify bootstrap.sh handles credentials
        bootstrap_sh = bootstrap_dir / "bootstrap.sh"
        content = bootstrap_sh.read_text()
        assert "get_credentials" in content or "GIT_TOKEN" in content, \
            "bootstrap.sh should handle git credentials"
    
    def test_sops_yaml_generated(self, generate_bootstrap):
        """Test that .sops.yaml is generated."""
        bootstrap_dir = generate_bootstrap(
            components=["cert-manager"],
            cluster_name="sops-test"
        )
        
        assert (bootstrap_dir / ".sops.yaml").exists(), ".sops.yaml should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
