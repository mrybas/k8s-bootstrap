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
import os
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime
import yaml

from app.core.config import settings
from app.core.definitions import get_categories
from app.generator.chart_generator import ChartGenerator
from app.generator.bootstrap_generator import BootstrapGenerator, GitAuthConfig
from app.generator.template_engine import render, render_to_file


class RepoGenerator:
    def __init__(
        self,
        output_dir: str,
        cluster_name: str,
        repo_url: str,
        branch: str = "main",
        vendor_charts: bool = False,
        git_auth: GitAuthConfig = None,
        skip_git_push: bool = False
    ):
        self.output_dir = Path(output_dir)
        self.cluster_name = cluster_name.lower().replace("_", "-").replace(" ", "-")
        self.repo_url = repo_url
        self.branch = branch
        self.vendor_charts = vendor_charts
        self.git_auth = git_auth
        self.skip_git_push = skip_git_push
        self.chart_generator = ChartGenerator(vendor_charts=vendor_charts)
        self.bootstrap_generator = BootstrapGenerator(
            cluster_name=self.cluster_name,
            repo_url=self.repo_url,
            branch=self.branch,
            vendor_charts=vendor_charts,
            git_auth=git_auth,
            skip_git_push=skip_git_push
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
            self.chart_generator.generate_chart(
                definition=defn,
                values={},  # No user values in chart - only defaults
                raw_overrides="",
                output_dir=charts_path / category
            )
        
        # Generate manifests
        self._generate_kustomization_manifests(repo_path, active_categories)
        self._generate_namespaces_manifests(repo_path, namespaces)
        self._generate_release_manifests(repo_path, components, components_by_category)
        
        # Generate supporting files
        self.bootstrap_generator.generate_bootstrap_script(repo_path, active_categories)
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
        """Get list of categories that have components, sorted by priority."""
        active = []
        for cat_id, cat_info in all_categories.items():
            if cat_id in components_by_category and len(components_by_category[cat_id]) > 0:
                active.append({
                    "name": cat_id,
                    "priority": cat_info.get("priority", 100),
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
        
        # Check if we have any CRD charts - they go to cluster-crds
        has_crds = any(comp["definition"]["id"].endswith("-crds") for comp in components)
        if has_crds and "cluster-crds" not in seen_ns:
            namespaces.append({"name": "cluster-crds"})
            seen_ns.add("cluster-crds")
        
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
            
            # CRD charts go to cluster-crds
            if comp_id.endswith("-crds"):
                continue
            
            # Handle multi-instance components (instance has custom namespace)
            instance_name = defn.get("_instance_name")
            if instance_name:
                target_ns = defn.get("namespace", instance_name)
            else:
                target_ns = defn.get("namespace", comp_id)
            
            if target_ns in skip_ns or target_ns in seen_ns:
                continue
            
            if not defn.get("createNamespace", True):
                continue
            
            namespaces.append({"name": target_ns})
            seen_ns.add(target_ns)
        
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
            
            # Skip meta-components (they don't have HelmReleases)
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
                    namespace = "cluster-crds"
                else:
                    namespace = defn.get("namespace", comp_id)
            
            # Build dependsOn
            depends_on = self._build_depends_on(defn, components)
            
            # Merge default values with user values
            default_values = defn.get("defaultValues", {})
            user_values = comp.get("values", {})
            raw_overrides = comp.get("raw_overrides", "")
            
            merged_values = self._merge_values(default_values, user_values, raw_overrides)
            
            # For wrapper charts, wrap values in upstream chart name
            # This is required because wrapper charts use dependencies
            if defn.get("chartType") != "custom" and merged_values:
                upstream = defn.get("upstream", {})
                upstream_name = upstream.get("chartName", comp_id)
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
                comp_ns_map[cid] = "cluster-crds"
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
        result = self._deep_merge(defaults.copy(), user)
        
        if raw and raw.strip():
            try:
                raw_parsed = yaml.safe_load(raw)
                if isinstance(raw_parsed, dict):
                    result = self._deep_merge(result, raw_parsed)
            except yaml.YAMLError:
                pass  # Ignore invalid YAML in raw overrides
        
        return result
    
    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = RepoGenerator._deep_merge(result[key], value)
            else:
                result[key] = value
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
            if defn.get("chartType") == "custom" or defn.get("bootstrapInstall"):
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
        
        content = render("scripts/vendor-charts.sh.j2", charts=charts)
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
            "selections": selections,  # Flat array as frontend expects
        }
        
        config_content = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
        (repo_path / "k8s-bootstrap.yaml").write_text(f'''# K8s Bootstrap Configuration v2.0
# Import this file to restore your selections
{config_content}''')
