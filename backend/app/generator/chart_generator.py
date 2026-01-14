"""
Chart Generator - Vendors upstream charts via helm pull

NOTE: In the new architecture, charts only contain DEFAULT values.
User values are stored in HelmRelease manifests (manifests/releases/<category>/<component>.yaml)
"""
import os
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any
import yaml


class ChartGenerator:
    """Generates Helm charts with optional upstream vendoring"""
    
    def __init__(self, vendor_charts: bool = False):
        """
        Args:
            vendor_charts: If True, download charts via helm pull.
                          If False, create placeholders (user runs vendor-charts.sh locally).
        """
        self.vendor_charts = vendor_charts
    
    def generate_chart(self, definition: Dict, values: Dict, raw_overrides: str, output_dir: Path) -> Path:
        chart_path = output_dir / definition["id"]
        chart_path.mkdir(parents=True, exist_ok=True)
        
        if definition.get("chartType") == "custom":
            self._gen_custom(definition, values, raw_overrides, chart_path)
        else:
            self._gen_wrapper(definition, values, raw_overrides, chart_path)
        return chart_path
    
    def _gen_wrapper(self, defn: Dict, values: Dict, raw: str, path: Path):
        """Generate wrapper chart + vendor upstream"""
        upstream = defn.get("upstream", {})
        name = upstream.get("chartName", defn["id"])
        version = upstream.get("version", "*")
        repo = upstream.get("repository", "")
        
        # Use upstream version for wrapper (strip 'v' prefix for SemVer compatibility)
        wrapper_version = version.lstrip("v") if version != "*" else "0.0.1"
        
        # Wrapper Chart.yaml
        self._yaml(path / "Chart.yaml", {
            "apiVersion": "v2",
            "name": defn["id"],
            "version": wrapper_version,
            "description": f"Wrapper for {defn['name']}",
            "dependencies": [{"name": name, "version": version, "repository": f"file://charts/{name}"}]
        })
        
        # Wrapped values
        merged = self._merge(defn.get("defaultValues", {}), values, raw)
        self._yaml(path / "values.yaml", {name: merged})
        
        # Vendor the actual chart (or create placeholder)
        charts_dir = path / "charts"
        charts_dir.mkdir(exist_ok=True)
        
        if self.vendor_charts:
            # Download chart on server
            self._vendor(repo, name, version, charts_dir, defn["id"])
        else:
            # Create placeholder - user will run vendor-charts.sh locally
            self._placeholder(charts_dir, name, version, repo, None)
    
    def _vendor(self, repo: str, name: str, version: str, out: Path, chart_id: str):
        """Download chart via helm pull"""
        is_oci = repo.startswith("oci://")
        
        try:
            with tempfile.TemporaryDirectory() as tmp:
                if is_oci:
                    cmd = ["helm", "pull", f"{repo}/{name}", "--version", version, "--untar", "--untardir", tmp]
                else:
                    # Add repo and pull
                    repo_name = chart_id.replace("-", "_")
                    subprocess.run(["helm", "repo", "add", repo_name, repo, "--force-update"], 
                                 capture_output=True, timeout=60)
                    subprocess.run(["helm", "repo", "update"], capture_output=True, timeout=60)
                    cmd = ["helm", "pull", f"{repo_name}/{name}", "--version", version, "--untar", "--untardir", tmp]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0:
                    # Find extracted chart
                    for item in Path(tmp).iterdir():
                        if item.is_dir():
                            dest = out / name
                            if dest.exists():
                                shutil.rmtree(dest)
                            shutil.copytree(item, dest)
                            return
                
                # Fallback to placeholder
                self._placeholder(out, name, version, repo, result.stderr)
                
        except Exception as e:
            self._placeholder(out, name, version, repo, str(e))
    
    def _placeholder(self, out: Path, name: str, ver: str, repo: str, err: str = None):
        """Create placeholder when download fails"""
        path = out / name
        path.mkdir(parents=True, exist_ok=True)
        
        # Strip 'v' prefix for SemVer compatibility
        chart_version = ver.lstrip("v") if ver != "*" else "0.0.1"
        self._yaml(path / "Chart.yaml", {"apiVersion": "v2", "name": name, "version": chart_version})
        self._yaml(path / "values.yaml", {})
        (path / "templates").mkdir(exist_ok=True)
        
        is_oci = repo.startswith("oci://")
        pull = f"helm pull {repo}/{name} --version {ver} --untar" if is_oci else \
               f"helm repo add {name} {repo} && helm pull {name}/{name} --version {ver} --untar"
        
        (path / "VENDOR_ME.md").write_text(f'''# {name} - NEEDS VENDORING

Run: `cd $(dirname $0) && {pull}`

Repo: {repo}
Version: {ver}
{"Error: " + err if err else ""}
''')
    
    def _gen_custom(self, defn: Dict, values: Dict, raw: str, path: Path):
        """Generate custom chart"""
        self._yaml(path / "Chart.yaml", {
            "apiVersion": "v2", "name": defn["id"], "version": "0.0.1",
            "description": defn.get("description", "")
        })
        self._yaml(path / "values.yaml", self._merge(defn.get("defaultValues", {}), values, raw))
        
        tpl = path / "templates"
        tpl.mkdir(exist_ok=True)
        for name, content in defn.get("templates", {}).items():
            (tpl / name).write_text(content)
        
        if defn["id"] == "namespaces" and not defn.get("templates"):
            (tpl / "namespaces.yaml").write_text('''{{- range .Values.namespaces }}
---
apiVersion: v1
kind: Namespace
metadata:
  name: {{ .name }}
  {{- with .labels }}
  labels: {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
''')
    
    def _merge(self, defaults: Dict, user: Dict, raw: str) -> Dict:
        result = self._deep(defaults.copy(), user)
        if raw and raw.strip():
            # Raw overrides should already be validated by API layer
            # but we still parse here - any error at this point is a bug
            r = yaml.safe_load(raw)
            if isinstance(r, dict):
                result = self._deep(result, r)
        return result
    
    @staticmethod
    def validate_raw_yaml(raw: str, component_id: str) -> tuple[bool, str | None]:
        """
        Validate raw YAML overrides.
        
        Returns:
            (is_valid, error_message) - error_message is None if valid
        """
        if not raw or not raw.strip():
            return True, None
        
        try:
            parsed = yaml.safe_load(raw)
            if parsed is None:
                return True, None  # Empty YAML is valid
            if not isinstance(parsed, dict):
                return False, f"Raw overrides for '{component_id}' must be a YAML mapping (key: value), got {type(parsed).__name__}"
            return True, None
        except yaml.YAMLError as e:
            # Extract useful error info
            if hasattr(e, 'problem_mark'):
                mark = e.problem_mark
                return False, f"Invalid YAML in raw overrides for '{component_id}': {e.problem} at line {mark.line + 1}, column {mark.column + 1}"
            return False, f"Invalid YAML in raw overrides for '{component_id}': {str(e)}"
    
    def _deep(self, base: Dict, over: Dict) -> Dict:
        result = base.copy()
        for k, v in over.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep(result[k], v)
            else:
                result[k] = v
        return result
    
    def _yaml(self, path: Path, data: dict):
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
