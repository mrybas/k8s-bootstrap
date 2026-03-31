"""
Repository Generator - Refactored Architecture

Structure:
  charts/
    <category>/
      <component>/           - Wrapper charts with defaults only
  manifests/
    kustomizations/          - Static Kustomization files for Flux
      00-namespaces.yaml     - Namespaces Kustomization (first)
      10-releases-core.yaml  - Core releases Kustomization
      XX-releases-<cat>.yaml - Per-category Kustomizations
    namespaces/              - HelmRelease for namespaces chart
      release.yaml
    releases/
      <category>/
        <component>.yaml     - HelmRelease with user values

Key Pattern:
- Kustomizations are static YAML files in manifests/kustomizations/
- HelmReleases are individual manifests in manifests/releases/<category>/
- User values are in HelmRelease manifests, NOT in chart values.yaml
- flux-instance chart only creates GitRepository (no Kustomizations)
"""
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime
import yaml

from app.core.config import settings
from app.core.definitions import get_categories, load_tenant_addons
from app.core.utils import deep_merge, sanitize_cluster_name
from app.generator.chart_generator import ChartGenerator
from app.generator.manifest_chart_generator import get_manifest_chart_generator
from app.generator.bootstrap_generator import BootstrapGenerator, GitAuthConfig
from app.generator.template_engine import render, render_to_file

logger = logging.getLogger("k8s_bootstrap.repo_generator")


class RepoGenerator:
    def __init__(
        self,
        output_dir: str,
        cluster_name: str,
        repo_url: str,
        branch: str = "main",
        vendor_charts: bool = False,
        git_auth: GitAuthConfig = None,
        skip_git_push: bool = False,
        cni_bootstrap_component: str = None,
        dns_bootstrap_component: str = None,
        bundle_config: dict = None
    ):
        self.output_dir = Path(output_dir)
        self.cluster_name = sanitize_cluster_name(cluster_name)
        self.repo_url = repo_url
        self.branch = branch
        self.vendor_charts = vendor_charts
        self.git_auth = git_auth
        self.skip_git_push = skip_git_push
        self.cni_bootstrap_component = cni_bootstrap_component
        self.dns_bootstrap_component = dns_bootstrap_component
        self.bundle_config = bundle_config
        self.chart_generator = ChartGenerator(vendor_charts=vendor_charts)
        self.bootstrap_generator = BootstrapGenerator(
            cluster_name=self.cluster_name,
            repo_url=self.repo_url,
            branch=self.branch,
            vendor_charts=vendor_charts,
            git_auth=git_auth,
            skip_git_push=skip_git_push,
            cni_bootstrap_component=cni_bootstrap_component,
            dns_bootstrap_component=dns_bootstrap_component
        )
    
    def generate(self, components: List[Dict[str, Any]]) -> str:
        """Generate complete repository structure."""
        repo_path = self.output_dir / self.cluster_name
        repo_path.mkdir(parents=True, exist_ok=True)
        
        # Get categories from definitions
        all_categories = get_categories()
        
        # Separate components by category
        components_by_category = self._group_by_category(components)
        
        # Get active categories (that have components)
        active_categories = self._get_active_categories(components_by_category, all_categories)
        
        # Create directories
        charts_path = repo_path / "charts"
        charts_path.mkdir(exist_ok=True)
        
        # Collect all namespaces
        namespaces = self._collect_namespaces(components)
        
        # Generate core charts (flux-operator, flux-instance, namespaces)
        # Note: flux-instance only creates GitRepository, Kustomizations are static files
        self.bootstrap_generator.generate_flux_operator(charts_path, category="core")
        self.bootstrap_generator.generate_flux_instance(charts_path, category="core")
        self._generate_namespaces_chart(charts_path, namespaces)
        
        # Get manifest chart generator
        manifest_chart_gen = get_manifest_chart_generator()
        
        # Generate component charts in category folders (defaults only)
        for comp in components:
            defn = comp["definition"]
            # Skip core components (flux-operator, flux-instance, namespaces)
            if defn.get("bootstrapInstall") or defn["id"] == "namespaces":
                continue
            # Skip meta-components (they only trigger autoInclude of other components)
            if defn.get("chartType") == "meta":
                continue
            
            category = defn.get("category", "apps")
            category_path = charts_path / category
            
            # Generate chart based on chartType
            chart_type = defn.get("chartType", "upstream")
            
            if chart_type in ("manifest", "custom"):
                # Check if bundled chart exists or has inline templates
                if manifest_chart_gen.has_bundled_chart(defn["id"]):
                    # Copy from bundled charts directory
                    manifest_chart_gen.generate_chart(
                        definition=defn,
                        output_dir=category_path
                    )
                else:
                    # Generate custom chart from inline templates
                    self.chart_generator.generate_chart(
                        definition=defn,
                        values={},
                        raw_overrides="",
                        output_dir=category_path
                    )
            else:
                # Upstream charts - generate wrapper chart
                self.chart_generator.generate_chart(
                    definition=defn,
                    values={},  # No user values in chart - only defaults
                    raw_overrides="",
                    output_dir=category_path
                )
        
        # Generate manifests
        self._generate_kustomization_manifests(repo_path, active_categories)
        self._generate_namespaces_manifests(repo_path, namespaces)
        self._generate_release_manifests(repo_path, components, components_by_category)
        
        # Detect if Cilium chaining mode is needed for bootstrap
        enabled_ids = {c["definition"]["id"] for c in components}
        if self.cni_bootstrap_component == "kube-ovn" and "cilium" in enabled_ids:
            self.bootstrap_generator.cni_chaining_with_cilium = True
        
        # Generate tenant addon templates (if multi-tenancy bundle)
        self._generate_tenant_addons(repo_path)
        
        # Generate supporting files
        self.bootstrap_generator.generate_bootstrap_script(repo_path, active_categories, [])
        self._generate_vendor_script(repo_path, components)
        self._generate_sops_config(repo_path)
        self._generate_readme(repo_path, components, active_categories)
        self._generate_gitignore(repo_path)
        self._generate_config_file(repo_path, components)
        
        return str(repo_path)
    
    def _group_by_category(self, components: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group components by their category."""
        result: Dict[str, List[Dict[str, Any]]] = {}
        for comp in components:
            defn = comp["definition"]
            category = defn.get("category", "apps")
            if category not in result:
                result[category] = []
            result[category].append(comp)
        return result
    
    def _get_active_categories(
        self, 
        components_by_category: Dict[str, List[Dict[str, Any]]], 
        all_categories: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get list of categories that have components, sorted by priority.
        
        Auto-discovers categories from components even if not in categories.yaml.
        """
        active = []
        for cat_id in components_by_category:
            if not components_by_category[cat_id]:
                continue
            cat_info = all_categories.get(cat_id)
            if cat_info:
                priority = cat_info.get("priority", 100)
            else:
                # Auto-discover: category exists in components but not in categories.yaml
                # Use component's own priority as hint, default to 90
                first_comp = components_by_category[cat_id][0]["definition"]
                priority = first_comp.get("priority", 90)
                logger.warning(
                    f"Category '{cat_id}' not found in categories.yaml — auto-discovered from components (priority={priority})"
                )
            active.append({
                "name": cat_id,
                "priority": priority,
            })
        # Sort by priority
        return sorted(active, key=lambda x: x["priority"])
    
    def _collect_namespaces(self, components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collect all namespaces needed for components."""
        namespaces: List[Dict[str, Any]] = []
        seen_ns: Set[str] = set()
        
        # System namespaces that should not be created
        skip_ns = {"default", "kube-system", "kube-public", "kube-node-lease", "flux-system"}
        seen_ns.add("flux-system")
        
        # Check if we have any CRD charts - they go to o0-crds
        has_crds = any(comp["definition"]["id"].endswith("-crds") for comp in components)
        if has_crds and "o0-crds" not in seen_ns:
            namespaces.append({"name": "o0-crds"})
            seen_ns.add("o0-crds")
        
        # Collect namespaces from components
        for comp in components:
            defn = comp["definition"]
            comp_id = defn["id"]
            
            # Skip bootstrap components
            if defn.get("bootstrapInstall") or comp_id == "namespaces":
                continue
            
            # Skip meta-components (they don't have namespaces)
            if defn.get("chartType") == "meta":
                continue
            
            # CRD charts go to o0-crds (already added above)
            if comp_id.endswith("-crds"):
                continue
            
            # Handle multi-instance components (instance has custom namespace)
            instance_name = defn.get("_instance_name")
            if instance_name:
                target_ns = defn.get("namespace", instance_name)
            else:
                target_ns = defn.get("namespace", comp_id)
            
            if target_ns in skip_ns:
                continue
            
            if not defn.get("createNamespace", True):
                continue
            
            # Add PodSecurity label if required
            pod_security = defn.get("podSecurityEnforce")
            
            # If namespace already seen, merge labels from this component
            if target_ns in seen_ns:
                if pod_security:
                    for ns_entry in namespaces:
                        if ns_entry["name"] == target_ns:
                            labels = ns_entry.setdefault("labels", {})
                            labels["pod-security.kubernetes.io/enforce"] = pod_security
                            labels["pod-security.kubernetes.io/audit"] = pod_security
                            labels["pod-security.kubernetes.io/warn"] = pod_security
                            break
                continue
            
            ns_entry = {"name": target_ns}
            if pod_security:
                ns_entry["labels"] = {
                    "pod-security.kubernetes.io/enforce": pod_security,
                    "pod-security.kubernetes.io/audit": pod_security,
                    "pod-security.kubernetes.io/warn": pod_security,
                }
            
            namespaces.append(ns_entry)
            seen_ns.add(target_ns)

            # Collect additional namespaces declared by the component
            for extra_ns in defn.get("additionalNamespaces", []):
                if extra_ns not in seen_ns and extra_ns not in skip_ns:
                    namespaces.append({"name": extra_ns})
                    seen_ns.add(extra_ns)

        return namespaces
    
    def _generate_namespaces_chart(self, charts_path: Path, namespaces: List[Dict[str, Any]]):
        """Generate charts/core/namespaces/ with all cluster namespaces."""
        core_path = charts_path / "core"
        core_path.mkdir(exist_ok=True)
        
        ns_chart_path = core_path / "namespaces"
        ns_chart_path.mkdir(exist_ok=True)
        (ns_chart_path / "templates").mkdir(exist_ok=True)
        
        # Use timestamp-based version to force Flux to detect changes
        chart_version = datetime.utcnow().strftime("0.1.%Y%m%d%H%M%S")
        render_to_file(
            "charts/namespaces/Chart.yaml.j2",
            ns_chart_path / "Chart.yaml",
            chart_version=chart_version
        )
        
        render_to_file(
            "charts/namespaces/values.yaml.j2",
            ns_chart_path / "values.yaml"
            # Note: namespaces are configured in HelmRelease, not here
        )
        
        render_to_file(
            "charts/namespaces/templates/namespaces.yaml.j2",
            ns_chart_path / "templates" / "namespaces.yaml"
        )
    
    def _generate_kustomization_manifests(self, repo_path: Path, active_categories: List[Dict[str, Any]]):
        """Generate static Kustomization files in manifests/kustomizations/."""
        kust_path = repo_path / "manifests" / "kustomizations"
        kust_path.mkdir(parents=True, exist_ok=True)
        
        # 00-namespaces.yaml - first, no dependencies
        render_to_file(
            "manifests/kustomizations/namespaces.yaml.j2",
            kust_path / "00-namespaces.yaml"
        )
        
        # Generate Kustomization for each active category
        prev_depends_on = "namespaces"
        for cat in active_categories:
            cat_name = cat["name"]
            priority = cat["priority"]
            
            # Generate XX-releases-<category>.yaml
            filename = f"{priority:02d}-releases-{cat_name}.yaml"
            render_to_file(
                "manifests/kustomizations/category.yaml.j2",
                kust_path / filename,
                category_name=cat_name,
                depends_on=prev_depends_on
            )
            
            # Next category depends on this one
            prev_depends_on = f"releases-{cat_name}"
    
    def _generate_namespaces_manifests(self, repo_path: Path, namespaces: List[Dict[str, Any]]):
        """Generate manifests/namespaces/ with HelmRelease for namespaces chart."""
        ns_path = repo_path / "manifests" / "namespaces"
        ns_path.mkdir(parents=True, exist_ok=True)
        
        # HelmRelease for namespaces chart with values
        render_to_file(
            "manifests/namespaces/release.yaml.j2",
            ns_path / "release.yaml",
            namespaces=namespaces
        )
    
    def _generate_release_manifests(
        self, 
        repo_path: Path, 
        components: List[Dict[str, Any]],
        components_by_category: Dict[str, List[Dict[str, Any]]]
    ):
        """Generate individual HelmRelease manifests in manifests/releases/<category>/"""
        releases_path = repo_path / "manifests" / "releases"
        
        for comp in components:
            defn = comp["definition"]
            comp_id = defn["id"]
            
            # Skip namespaces (has its own manifest location)
            if comp_id == "namespaces":
                continue
            
            # Skip meta-components (only trigger autoInclude of other components)
            if defn.get("chartType") == "meta":
                continue
            
            category = defn.get("category", "apps")
            category_path = releases_path / category
            category_path.mkdir(parents=True, exist_ok=True)
            
            # Handle multi-instance components
            instance_name = defn.get("_instance_name")
            if instance_name:
                # Multi-instance: use instance-specific naming
                release_id = f"{comp_id}-{instance_name}"
                namespace = defn.get("namespace", instance_name)
            else:
                # Single instance (default)
                release_id = comp_id
                if comp_id.endswith("-crds"):
                    namespace = "o0-crds"
                else:
                    namespace = defn.get("namespace", comp_id)
            
            # Build dependsOn
            depends_on = self._build_depends_on(defn, components)
            
            chart_type = defn.get("chartType")
            
            # All chart types: merge default values with user values
            # Chart values.yaml is empty - all config lives in HelmRelease
            default_values = defn.get("defaultValues", {})
            user_values = comp.get("values", {})
            raw_overrides = comp.get("raw_overrides", "")
            
            merged_values = self._merge_values(default_values, user_values, raw_overrides)
            
            # Merge wrapperValues defaults into merged_values.
            # wrapperValues are for wrapper chart's own templates (e.g. ServiceMonitor).
            # They were previously in chart values.yaml; now they go into HelmRelease.
            # Merged BEFORE dynamic overrides so user values can override wrapper defaults.
            wrapper_defaults = defn.get("wrapperValues", {})
            if wrapper_defaults:
                merged_values = deep_merge(wrapper_defaults, merged_values)
            
            # Dynamic values: Cilium chaining mode with Kube-OVN
            # Applied AFTER user merge so chaining overrides take precedence
            if comp_id == "cilium":
                enabled_ids = {c["definition"]["id"] for c in components}
                if "kube-ovn" in enabled_ids and "cilium-cni-chaining" in enabled_ids:
                    chaining_values = {
                        "cni": {
                            "chainingMode": "generic-veth",
                            "customConf": True,
                            "configMap": "cni-configuration",
                            "exclusive": False,
                        },
                        "routingMode": "native",
                        "enableIPv4Masquerade": False,
                        "enableIdentityMark": False,
                        "enableSourceIpVerification": False,
                        # Network interfaces: eth+ eno+ ens+ enp+ for physical/virtual NICs
                        # ovn0, genev_sys_6081, vxlan_sys_4789 for Kube-OVN tunnels
                        "devices": "eth+ eno+ ens+ enp+ ovn0 genev_sys_6081 vxlan_sys_4789",
                        "ipam": {"mode": "cluster-pool"}
                    }
                    merged_values = deep_merge(merged_values, chaining_values)
            
            # For wrapper (upstream) charts, wrap values in upstream chart name
            # This is required because wrapper charts use Helm dependencies
            # Skip for custom and manifest charts - they have their own structure
            if chart_type not in ("custom", "manifest") and merged_values:
                upstream = defn.get("upstream", {})
                upstream_name = upstream.get("chartName", comp_id)
                
                # Split values: wrapper keys stay top-level, rest gets wrapped
                # wrapperValues define keys that belong to the wrapper chart's own templates
                wrapper_keys = set(wrapper_defaults.keys()) if wrapper_defaults else set()
                if wrapper_keys:
                    upstream_vals = {k: v for k, v in merged_values.items() if k not in wrapper_keys}
                    wrapper_vals = {k: v for k, v in merged_values.items() if k in wrapper_keys}
                    merged_values = {upstream_name: upstream_vals} if upstream_vals else {}
                    merged_values.update(wrapper_vals)
                else:
                    merged_values = {upstream_name: merged_values}
            
            # Generate HelmRelease manifest
            render_to_file(
                "manifests/releases/helmrelease.yaml.j2",
                category_path / f"{release_id}.yaml",
                name=release_id,
                namespace=namespace,
                category=category,
                chart_name=comp_id,  # Chart path stays the same
                release_name=defn.get("releaseName", release_id),
                timeout=defn.get("timeout", "10m"),
                depends_on=depends_on,
                values=merged_values if merged_values else None
            )
    
    def _build_depends_on(self, defn: Dict[str, Any], all_components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build dependsOn list for a component."""
        deps = defn.get("dependsOn", [])
        if not deps:
            return []
        
        result = []
        
        # Build a map of component id -> namespace
        comp_ns_map = {}
        for comp in all_components:
            d = comp["definition"]
            cid = d["id"]
            if cid.endswith("-crds"):
                comp_ns_map[cid] = "o0-crds"
            else:
                comp_ns_map[cid] = d.get("namespace", cid)
        
        for dep_id in deps:
            # Skip flux dependencies (handled at Kustomization level)
            if dep_id.startswith("flux-") or dep_id == "namespaces":
                continue
            
            dep_entry = {"name": dep_id}
            if dep_id in comp_ns_map:
                dep_entry["namespace"] = comp_ns_map[dep_id]
            
            result.append(dep_entry)
        
        return result
    
    def _merge_values(self, defaults: Dict, user: Dict, raw: str) -> Dict:
        """Merge default values with user values and raw overrides."""
        result = deep_merge(defaults.copy(), user)
        
        if raw and raw.strip():
            try:
                raw_parsed = yaml.safe_load(raw)
                if isinstance(raw_parsed, dict):
                    result = deep_merge(result, raw_parsed)
            except yaml.YAMLError:
                logger.warning("Invalid YAML in raw overrides, ignoring")
        
        return result
    
    def _generate_vendor_script(self, repo_path: Path, components: List[Dict[str, Any]]):
        """Generate vendor-charts.sh for chart vendoring."""
        charts = []
        
        # Add flux-operator
        charts.append({
            "id": "flux-operator",
            "category": "core",
            "name": "flux-operator",
            "version": self.bootstrap_generator.FLUX_OPERATOR_VERSION,
            "repository": "oci://ghcr.io/controlplaneio-fluxcd/charts"
        })
        
        # Add component charts
        for comp in components:
            defn = comp["definition"]
            # Skip custom, bootstrap, and manifest-based components
            if defn.get("chartType") in ("custom", "manifest") or defn.get("bootstrapInstall"):
                continue
            
            upstream = defn.get("upstream", {})
            if not upstream.get("repository"):
                continue
            
            charts.append({
                "id": defn["id"],
                "category": defn.get("category", "apps"),
                "name": upstream.get("chartName", defn["id"]),
                "version": upstream.get("version", "latest"),
                "repository": upstream["repository"]
            })
        
        # Add tenant addon charts (resolved by _generate_tenant_addons)
        tenant_charts = getattr(self, '_tenant_chart_specs', [])
        
        content = render("scripts/vendor-charts.sh.j2", charts=charts, tenant_charts=tenant_charts)
        script_path = repo_path / "vendor-charts.sh"
        script_path.write_text(content)
        os.chmod(script_path, 0o755)
    
    def _generate_sops_config(self, repo_path: Path):
        """Generate .sops.yaml configuration."""
        content = '''# SOPS configuration
# Update AGE_PUBLIC_KEY with your key from .age/key.pub
creation_rules:
  - path_regex: .*\\.enc\\.yaml$
    encrypted_regex: "^(data|stringData)$"
    age: AGE_PUBLIC_KEY
  - path_regex: secrets/.*\\.yaml$
    encrypted_regex: "^(data|stringData)$"
    age: AGE_PUBLIC_KEY
'''
        (repo_path / ".sops.yaml").write_text(content)
    
    def _generate_readme(self, repo_path: Path, components: List[Dict[str, Any]], categories: List[Dict[str, Any]]):
        """Generate README.md."""
        # Group components by category for display
        by_cat: Dict[str, List[str]] = {}
        for comp in components:
            defn = comp["definition"]
            if defn.get("bootstrapInstall") or defn["id"] == "namespaces":
                continue
            cat = defn.get("category", "apps")
            if cat not in by_cat:
                by_cat[cat] = []
            version = defn.get("upstream", {}).get("version", "custom")
            by_cat[cat].append(f"- **{defn['name']}** (v{version})")
        
        comp_section = ""
        for cat in categories:
            cat_name = cat["name"]
            if cat_name in by_cat:
                comp_section += f"\n### {cat_name.title()}\n\n"
                comp_section += "\n".join(by_cat[cat_name]) + "\n"
        
        content = f'''# {self.cluster_name} - Kubernetes GitOps Bootstrap

Generated by K8s Bootstrap on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Components
{comp_section}

## Quick Start

```bash
# 1. Vendor charts (download upstream charts)
./vendor-charts.sh

# 2. Run bootstrap
./bootstrap.sh

# 3. Monitor
kubectl get kustomizations,helmreleases -A
```

## Structure

```
charts/
├── core/                    # Core infrastructure
│   ├── flux-operator/       # Flux Operator
│   ├── flux-instance/       # GitOps config (GitRepository only)
│   └── namespaces/          # All cluster namespaces
├── system/                  # System components
├── observability/           # Monitoring & logging
└── ...                      # Other categories

manifests/
├── kustomizations/          # Static Kustomization files (NOT generated by Helm)
│   ├── 00-namespaces.yaml   # Watches manifests/namespaces/
│   ├── 10-releases-core.yaml # Watches manifests/releases/core/
│   ├── 30-releases-system.yaml
│   └── ...
├── namespaces/              # HelmRelease for namespaces chart
│   └── release.yaml
└── releases/                # All component HelmReleases
    ├── core/
    │   ├── flux-operator.yaml
    │   └── flux-instance.yaml
    ├── system/
    │   └── metrics-server.yaml
    └── ...
```

## Key Concepts

1. **Static Kustomizations**: All Kustomization files are plain YAML in `manifests/kustomizations/`
2. **Namespaces first**: Kustomization "namespaces" creates all NS before components
3. **HelmReleases in manifests/**: Each component has its own HelmRelease file
4. **Values in HelmRelease**: User values are in manifest files, NOT in chart values.yaml
5. **Categories**: Components organized by category with numbered Kustomizations for order

## Adding Components

1. Add namespace to `charts/core/namespaces/values.yaml`
2. Vendor the chart to `charts/<category>/<name>/`
3. Create HelmRelease in `manifests/releases/<category>/<name>.yaml`
4. (If new category) Add Kustomization in `manifests/kustomizations/XX-releases-<category>.yaml`
5. Commit and push

## Security

- `.age/key.txt` - SOPS private key (gitignored)
- SSH keys created in `~/.ssh/flux-{self.cluster_name}`
'''
        (repo_path / "README.md").write_text(content)
    
    def _generate_gitignore(self, repo_path: Path):
        """Generate .gitignore."""
        content = '''.DS_Store
*.swp
.idea/
.vscode/

# SECURITY - Never commit private keys!
.age/key.txt
*.agekey
*.pem
id_*
!*.pub
secrets/
*.key
*.secret

# Temp files from bootstrap
.flux-*.yaml
*.tmp

# Helm
.cache/
*.tgz
'''
        (repo_path / ".gitignore").write_text(content)
        
        # Create .age directory
        age_dir = repo_path / ".age"
        age_dir.mkdir(exist_ok=True)
        (age_dir / ".gitkeep").write_text("# Age keys directory\n")
    
    def _generate_tenant_addons(self, repo_path: Path):
        """Generate tenant-charts/ from components with tenantAddon: true.
        
        Reads chart spec from component's upstream: field (unified source of truth).
        Reads tenant-specific config from component's tenantConfig: field.
        
        Creates:
          tenant-charts/{category}/{id}/                     - Wrapper chart
          tenant-charts/catalog.yaml                         - Reference catalog
          manifests/releases/multi-tenancy/tenant-addon-catalog.yaml - ConfigMap for Flux
        """
        addons = load_tenant_addons()
        if not addons:
            return
        
        tenant_charts_path = repo_path / "tenant-charts"
        catalog_components = []
        self._tenant_chart_specs = []
        
        for defn in addons:
            addon_id = defn["id"]
            category = defn.get("category", "misc")
            tc = defn.get("tenantConfig", {})
            upstream = defn.get("upstream", {})
            
            # Chart spec comes from component's upstream: field
            repo = upstream.get("repository", "")
            chart_name = upstream.get("chartName", addon_id)
            version = upstream.get("version", "latest")
            
            # Custom charts (tenant-namespaces) don't need vendoring
            chart_type = defn.get("chartType", "upstream")
            
            if chart_type == "custom":
                # Generate custom chart with inline templates
                chart_path = tenant_charts_path / category / addon_id
                chart_path.mkdir(parents=True, exist_ok=True)
                self._yaml(chart_path / "Chart.yaml", {
                    "apiVersion": "v2",
                    "name": addon_id,
                    "version": "0.0.1",
                    "description": defn.get("description", ""),
                })
                self._yaml(chart_path / "values.yaml", tc.get("defaultValues", {}))
                # Copy inline templates
                tpl_dir = chart_path / "templates"
                tpl_dir.mkdir(exist_ok=True)
                for tpl_name, content in defn.get("templates", {}).items():
                    (tpl_dir / tpl_name).write_text(content)
                logger.info(f"Generated tenant-charts/{category}/{addon_id}/ (custom)")
            elif repo:
                # Generate wrapper chart with upstream dependency
                chart_path = tenant_charts_path / category / addon_id
                chart_path.mkdir(parents=True, exist_ok=True)
                
                wrapper_version = version.lstrip("v") if version != "latest" else "0.0.1"
                self._yaml(chart_path / "Chart.yaml", {
                    "apiVersion": "v2",
                    "name": addon_id,
                    "version": wrapper_version,
                    "description": defn.get("description", ""),
                    "dependencies": [{
                        "name": chart_name,
                        "version": version,
                        "repository": f"file://charts/{chart_name}"
                    }]
                })
                self._yaml(chart_path / "values.yaml", tc.get("defaultValues", {}))
                (chart_path / "charts").mkdir(exist_ok=True)
                
                self._tenant_chart_specs.append({
                    "id": addon_id, "category": category,
                    "name": chart_name, "version": version, "repository": repo,
                })
                logger.info(f"Generated tenant-charts/{category}/{addon_id}/ (upstream: {chart_name}@{version})")
            else:
                logger.warning(f"Tenant addon '{addon_id}': no chart source, skipping")
                continue
            
            # Build catalog entry (matches ConfigMap schema expected by kubevirt-ui)
            chart_rel = f"{category}/{addon_id}"
            catalog_components.append({
                "id": addon_id,
                "name": defn.get("name", addon_id),
                "category": category,
                "description": defn.get("description", ""),
                "required": tc.get("required", False),
                "default": tc.get("default", False),
                "chartPath": chart_rel,
                "namespace": tc.get("namespace", addon_id),
                "discovery_type": tc.get("discovery_type", ""),
                "defaultValues": tc.get("defaultValues", {}),
                "parameters": tc.get("parameters", []),
            })
        
        # Write catalog.yaml in tenant-charts/ (for reference)
        catalog = {"basePath": "tenant-charts", "components": catalog_components}
        (tenant_charts_path / "catalog.yaml").write_text(
            yaml.dump(catalog, default_flow_style=False, allow_unicode=True, sort_keys=False)
        )
        
        # Generate ConfigMap manifest for Flux to deploy into cluster
        configmap_catalog = {
            "gitRepositoryRef": {"name": "flux-system", "namespace": "flux-system"},
            "basePath": "tenant-charts",
            "components": catalog_components,
        }
        configmap_data = yaml.dump(
            configmap_catalog, default_flow_style=False, allow_unicode=True, sort_keys=False
        )
        configmap_manifest = f'''apiVersion: v1
kind: ConfigMap
metadata:
  name: tenant-addon-catalog
  namespace: flux-system
data:
  catalog.yaml: |
{self._indent(configmap_data, 4)}'''
        
        mt_path = repo_path / "manifests" / "releases" / "multi-tenancy"
        mt_path.mkdir(parents=True, exist_ok=True)
        (mt_path / "tenant-addon-catalog.yaml").write_text(configmap_manifest)
        logger.info(f"Generated tenant-addon-catalog ConfigMap ({len(catalog_components)} addons)")
    
    @staticmethod
    def _indent(text: str, spaces: int) -> str:
        """Indent every line of text by N spaces."""
        prefix = " " * spaces
        return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())
    
    @staticmethod
    def _yaml(path: Path, data: dict):
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def _generate_config_file(self, repo_path: Path, components: List[Dict[str, Any]]):
        """Generate k8s-bootstrap.yaml for re-import."""
        # Create flat selections list (frontend expects this format)
        selections: List[Dict] = []
        
        for comp in components:
            defn = comp["definition"]
            selections.append({
                "id": defn["id"],
                "enabled": True,
                "values": comp.get("values", {}),
                "rawOverrides": comp.get("raw_overrides", ""),
            })
        
        config = {
            "version": "2.0",  # New version for new structure
            "created_at": datetime.now().isoformat(),
            "cluster_name": self.cluster_name,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "cni_bootstrap": self.cni_bootstrap_component,
            "dns_bootstrap": self.dns_bootstrap_component,
            "selections": selections,  # Flat array as frontend expects
        }
        
        # Save bundle wizard state for re-import
        if self.bundle_config:
            config["bundle_config"] = self.bundle_config
        
        config_content = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
        (repo_path / "k8s-bootstrap.yaml").write_text(f'''# K8s Bootstrap Configuration v2.0
# Import this file to restore your selections
{config_content}''')
