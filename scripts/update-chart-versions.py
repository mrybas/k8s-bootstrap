#!/usr/bin/env python3
"""
Update Helm chart versions in component definitions.

This script:
1. Reads all component definitions from backend/definitions/components/
2. Queries upstream registries for latest versions
3. Validates defaultValues against chart schemas
4. Shows current vs latest versions
5. Optionally updates the definition files

Usage:
    python scripts/update-chart-versions.py              # Show versions only
    python scripts/update-chart-versions.py --update     # Update definitions
    python scripts/update-chart-versions.py --validate   # Validate values against schemas
    python scripts/update-chart-versions.py --json       # Output as JSON
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import yaml

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


DEFINITIONS_DIR = Path(__file__).parent.parent / "backend" / "definitions" / "components"
CATEGORIES_FILE = Path(__file__).parent.parent / "backend" / "definitions" / "categories.yaml"


def load_categories() -> Dict[str, Any]:
    """Load categories configuration."""
    if CATEGORIES_FILE.exists():
        try:
            with open(CATEGORIES_FILE) as f:
                data = yaml.safe_load(f)
                return data.get("categories", {})
        except Exception:
            pass
    return {}


def get_latest_version_oci(registry: str, chart: str) -> Optional[str]:
    """Get latest version from OCI registry."""
    try:
        # helm show chart oci://registry/chart --version latest doesn't work
        # Use helm pull --version to get available versions
        cmd = ["helm", "show", "chart", f"oci://{registry}/{chart}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            # Parse version from Chart.yaml output
            for line in result.stdout.split('\n'):
                if line.startswith('version:'):
                    return line.split(':')[1].strip()
    except Exception as e:
        print(f"  ⚠️  Error querying OCI {registry}/{chart}: {e}", file=sys.stderr)
    return None


def get_latest_version_helm_repo(repo_url: str, chart: str) -> Optional[str]:
    """Get latest version from Helm repository."""
    try:
        # Add repo temporarily
        repo_name = f"tmp-{chart.replace('/', '-')}"
        subprocess.run(
            ["helm", "repo", "add", repo_name, repo_url, "--force-update"],
            capture_output=True, timeout=30
        )
        subprocess.run(["helm", "repo", "update", repo_name], capture_output=True, timeout=60)
        
        # Search for chart
        result = subprocess.run(
            ["helm", "search", "repo", f"{repo_name}/{chart}", "--versions", "-o", "json"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            versions = json.loads(result.stdout)
            if versions:
                # First result is the latest
                return versions[0].get("version")
        
        # Cleanup
        subprocess.run(["helm", "repo", "remove", repo_name], capture_output=True, timeout=10)
    except Exception as e:
        print(f"  ⚠️  Error querying {repo_url}/{chart}: {e}", file=sys.stderr)
    return None


def get_latest_version(upstream_config: Dict[str, Any]) -> Optional[str]:
    """Get latest version for a chart based on its configuration."""
    repo = upstream_config.get("repository", "")
    chart = upstream_config.get("chartName", "") or upstream_config.get("chart", "")
    
    if not repo or not chart:
        return None
    
    # OCI registries
    if repo.startswith("oci://"):
        registry = repo.replace("oci://", "")
        return get_latest_version_oci(registry, chart)
    
    # Standard Helm repositories
    return get_latest_version_helm_repo(repo, chart)


def load_definition(path: Path) -> Optional[Dict[str, Any]]:
    """Load a component definition YAML file."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}", file=sys.stderr)
        return None


def pull_chart(upstream_config: Dict[str, Any], dest_dir: Path) -> Optional[Path]:
    """Pull a chart to a directory and return the extracted path."""
    repo = upstream_config.get("repository", "")
    chart = upstream_config.get("chartName", "") or upstream_config.get("chart", "")
    version = upstream_config.get("version", "")
    
    if not repo or not chart:
        return None
    
    try:
        if repo.startswith("oci://"):
            # OCI registry
            cmd = ["helm", "pull", f"{repo}/{chart}", "--version", version, "--untar", "--untardir", str(dest_dir)]
        else:
            # Standard repo - add it first
            repo_name = f"tmp-validate-{chart.replace('/', '-')}"
            subprocess.run(
                ["helm", "repo", "add", repo_name, repo, "--force-update"],
                capture_output=True, timeout=30
            )
            subprocess.run(["helm", "repo", "update", repo_name], capture_output=True, timeout=60)
            cmd = ["helm", "pull", f"{repo_name}/{chart}", "--version", version, "--untar", "--untardir", str(dest_dir)]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            # Find the extracted chart directory
            for item in dest_dir.iterdir():
                if item.is_dir():
                    return item
        else:
            print(f"    ⚠️  Failed to pull chart: {result.stderr[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"    ⚠️  Error pulling chart: {e}", file=sys.stderr)
    
    return None


def validate_values_against_schema(chart_path: Path, values: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate values against chart's values.schema.json."""
    errors = []
    schema_path = chart_path / "values.schema.json"
    
    if not schema_path.exists():
        return True, ["No schema file found (values.schema.json)"]
    
    if not HAS_JSONSCHEMA:
        return True, ["jsonschema library not installed, skipping JSON schema validation"]
    
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        
        validator = jsonschema.Draft7Validator(schema)
        for error in validator.iter_errors(values):
            path = " -> ".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"{path}: {error.message}")
        
        return len(errors) == 0, errors
    except Exception as e:
        return False, [f"Schema validation error: {e}"]


def validate_with_helm_template(chart_path: Path, values: Dict[str, Any], release_name: str = "test-release") -> Tuple[bool, List[str]]:
    """Validate values by running helm template."""
    errors = []
    
    try:
        # Write values to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(values, f)
            values_file = f.name
        
        try:
            # Run helm template with the specified release name
            result = subprocess.run(
                ["helm", "template", release_name, str(chart_path), "-f", values_file],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode != 0:
                # Extract meaningful errors
                for line in result.stderr.split('\n'):
                    if line.strip() and not line.startswith('coalesce'):
                        errors.append(line.strip())
            
            return result.returncode == 0, errors
        finally:
            os.unlink(values_file)
    except Exception as e:
        return False, [f"Helm template error: {e}"]


def validate_with_helm_lint(chart_path: Path, values: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate chart with helm lint."""
    errors = []
    
    try:
        # Write values to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(values, f)
            values_file = f.name
        
        try:
            result = subprocess.run(
                ["helm", "lint", str(chart_path), "-f", values_file],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode != 0:
                for line in result.stderr.split('\n') + result.stdout.split('\n'):
                    if '[ERROR]' in line or '[WARNING]' in line:
                        errors.append(line.strip())
            
            return result.returncode == 0, errors
        finally:
            os.unlink(values_file)
    except Exception as e:
        return False, [f"Helm lint error: {e}"]


def get_schema_allowed_properties(schema: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    """Recursively get allowed properties from schema."""
    result = {}
    
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        
        result["_additional"] = additional
        for prop_name, prop_schema in props.items():
            result[prop_name] = get_schema_allowed_properties(prop_schema, f"{path}.{prop_name}")
    
    return result


def filter_values_by_schema(values: Dict[str, Any], schema: Dict[str, Any], path: str = "") -> Tuple[Dict[str, Any], List[str]]:
    """Filter values to only include properties allowed by schema. Returns (filtered_values, removed_paths)."""
    if not isinstance(values, dict):
        return values, []
    
    removed = []
    filtered = {}
    
    # Get allowed properties from schema
    if schema.get("type") != "object":
        return values, []
    
    allowed_props = schema.get("properties", {})
    additional_allowed = schema.get("additionalProperties", True)
    
    for key, value in values.items():
        full_path = f"{path}.{key}" if path else key
        
        if key in allowed_props:
            # Property is in schema, recurse if it's an object
            prop_schema = allowed_props[key]
            if isinstance(value, dict) and prop_schema.get("type") == "object":
                filtered_value, sub_removed = filter_values_by_schema(value, prop_schema, full_path)
                if filtered_value:  # Only include if not empty after filtering
                    filtered[key] = filtered_value
                removed.extend(sub_removed)
            else:
                filtered[key] = value
        elif additional_allowed is True or (isinstance(additional_allowed, dict)):
            # Additional properties allowed
            filtered[key] = value
        else:
            # Property not allowed, remove it
            removed.append(full_path)
    
    return filtered, removed


def get_required_from_schema(schema: Dict[str, Any], chart_values: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    """Get required properties from schema that are missing, using chart's default values."""
    result = {}
    
    if schema.get("type") != "object":
        return result
    
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    for req_prop in required:
        if req_prop in chart_values:
            # Use the chart's default value for required property
            result[req_prop] = chart_values[req_prop]
    
    return result


def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge overlay into base, overlay values take precedence."""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_required_properties(values: Dict[str, Any], schema: Dict[str, Any], chart_values: Dict[str, Any], path: str = "") -> Tuple[Dict[str, Any], List[str]]:
    """Merge required properties from chart_values into values based on schema."""
    added = []
    
    if schema.get("type") != "object":
        return values, added
    
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    result = dict(values) if values else {}
    
    # For each property in schema, check if required or has required nested properties
    for prop_name, prop_schema in properties.items():
        full_path = f"{path}.{prop_name}" if path else prop_name
        nested_chart_values = chart_values.get(prop_name, {}) if isinstance(chart_values, dict) else {}
        
        if prop_name in required and prop_name not in result:
            # Required property missing entirely, add from chart defaults
            if prop_name in chart_values:
                result[prop_name] = chart_values[prop_name]
                added.append(full_path)
        
        if prop_schema.get("type") == "object":
            # Check if this object has required nested properties
            nested_required = prop_schema.get("required", [])
            
            if prop_name in result and isinstance(result[prop_name], dict):
                # Property exists, check for missing nested required properties
                our_values = result[prop_name]
                
                # Add missing nested required properties from chart defaults
                for nested_req in nested_required:
                    nested_full_path = f"{full_path}.{nested_req}"
                    if nested_req not in our_values and nested_req in nested_chart_values:
                        our_values[nested_req] = nested_chart_values[nested_req]
                        added.append(nested_full_path)
                
                # Recurse deeper
                result[prop_name], sub_added = merge_required_properties(
                    our_values, prop_schema, nested_chart_values, full_path
                )
                added.extend(sub_added)
            elif prop_name in required and nested_chart_values:
                # Required object missing, add it entirely from chart defaults
                result[prop_name] = nested_chart_values
                added.append(full_path)
    
    return result, added


def get_nested_value(d: Dict[str, Any], path: str) -> Any:
    """Get a nested value from dict using dot notation path."""
    keys = path.split('.')
    result = d
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return None
    return result


def set_nested_value(d: Dict[str, Any], path: str, value: Any):
    """Set a nested value in dict using dot notation path."""
    keys = path.split('.')
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


def fix_values_against_schema(chart_path: Path, values: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Fix values by removing disallowed properties and adding required ones.
    
    Returns: (fixed_values, removed_properties, added_properties)
    """
    schema_path = chart_path / "values.schema.json"
    values_path = chart_path / "values.yaml"
    
    removed = []
    added = []
    fixed_values = dict(values) if values else {}
    
    # Load chart's default values
    chart_values = {}
    if values_path.exists():
        try:
            with open(values_path) as f:
                chart_values = yaml.safe_load(f) or {}
        except Exception:
            pass
    
    if not schema_path.exists():
        return values, [], []
    
    if not HAS_JSONSCHEMA:
        return values, [], []
    
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        
        # Step 1: Remove disallowed properties
        fixed_values, removed = filter_values_by_schema(fixed_values, schema)
        
        # Step 2: Add missing required properties by parsing validation errors
        max_iterations = 10  # Prevent infinite loops
        for _ in range(max_iterations):
            validator = jsonschema.Draft7Validator(schema)
            errors = list(validator.iter_errors(fixed_values))
            
            if not errors:
                break
            
            fixed_this_round = False
            for error in errors:
                # Handle "required property" errors
                if "'required'" in str(error.validator) or "is a required property" in error.message:
                    # Parse the path and missing property from error
                    path = ".".join(str(p) for p in error.absolute_path)
                    
                    # Extract property name from message like "'image' is a required property"
                    import re
                    match = re.search(r"'(\w+)' is a required property", error.message)
                    if match:
                        missing_prop = match.group(1)
                        full_path = f"{path}.{missing_prop}" if path else missing_prop
                        
                        # Get value from chart defaults
                        default_value = get_nested_value(chart_values, full_path)
                        if default_value is not None:
                            set_nested_value(fixed_values, full_path, default_value)
                            added.append(full_path)
                            fixed_this_round = True
                
                # Handle "additional properties not allowed" errors
                elif "Additional properties are not allowed" in error.message:
                    match = re.search(r"\('([^']+)' was unexpected\)", error.message)
                    if match:
                        extra_prop = match.group(1)
                        path = ".".join(str(p) for p in error.absolute_path)
                        full_path = f"{path}.{extra_prop}" if path else extra_prop
                        
                        # Remove the property
                        keys = full_path.split('.')
                        obj = fixed_values
                        for key in keys[:-1]:
                            if key in obj:
                                obj = obj[key]
                            else:
                                break
                        else:
                            if keys[-1] in obj:
                                del obj[keys[-1]]
                                if full_path not in removed:
                                    removed.append(full_path)
                                fixed_this_round = True
            
            if not fixed_this_round:
                break
        
        return fixed_values, removed, added
    except Exception as e:
        print(f"    ⚠️  Error in fix: {e}", file=sys.stderr)
        return values, [], []


def validate_component(definition: Dict[str, Any], component_id: str, fix: bool = False) -> Dict[str, Any]:
    """Validate a component's defaultValues against its chart."""
    result = {
        "id": component_id,
        "valid": True,
        "schema_valid": None,
        "template_valid": None,
        "lint_valid": None,
        "errors": [],
        "fixed": False,
        "removed_properties": [],
        # Component metadata
        "category": definition.get("category", "unknown"),
        "isOperator": definition.get("isOperator", False),
        "multiInstance": definition.get("multiInstance", False),
        "requiresOperator": definition.get("requiresOperator"),
    }
    
    upstream_config = definition.get("upstream", {}) or definition.get("helm", {})
    default_values = definition.get("defaultValues", {})
    release_name = definition.get("releaseName", component_id)
    
    if not upstream_config.get("repository"):
        result["errors"].append("No upstream repository configured")
        return result
    
    # Create temp directory for chart
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        print(f"  📥 Pulling chart...", end=" ", flush=True)
        chart_path = pull_chart(upstream_config, tmp_path)
        
        if not chart_path:
            result["valid"] = False
            result["errors"].append("Failed to pull chart")
            print("❌")
            return result
        
        print("✓")
        
        # If fix mode, first try to fix values
        if fix:
            print(f"  🔧 Checking for schema issues...", end=" ", flush=True)
            fixed_values, removed, added = fix_values_against_schema(chart_path, default_values)
            if removed or added:
                changes = len(removed) + len(added)
                print(f"found {changes} change(s)")
                for prop in removed:
                    print(f"      ❌ Removing: {prop}")
                for prop in added:
                    print(f"      ✅ Adding: {prop}")
                default_values = fixed_values
                result["fixed"] = True
                result["removed_properties"] = removed
                result["added_properties"] = added
            else:
                print("none found")
        
        # 1. Validate against JSON schema
        print(f"  📋 Checking JSON schema...", end=" ", flush=True)
        schema_valid, schema_errors = validate_values_against_schema(chart_path, default_values)
        result["schema_valid"] = schema_valid
        if not schema_valid:
            result["valid"] = False
            result["errors"].extend([f"Schema: {e}" for e in schema_errors])
            print(f"❌ ({len(schema_errors)} errors)")
            for err in schema_errors[:3]:
                print(f"      {err[:100]}")
        else:
            print(f"✓" if not schema_errors else f"⏭️  {schema_errors[0][:50]}")
        
        # 2. Validate with helm template
        print(f"  🔧 Testing helm template...", end=" ", flush=True)
        template_valid, template_errors = validate_with_helm_template(chart_path, default_values, release_name)
        result["template_valid"] = template_valid
        if not template_valid:
            result["valid"] = False
            result["errors"].extend([f"Template: {e}" for e in template_errors])
            print(f"❌")
            for err in template_errors[:3]:
                print(f"      {err[:100]}")
        else:
            print("✓")
        
        # 3. Validate with helm lint
        print(f"  🔍 Running helm lint...", end=" ", flush=True)
        lint_valid, lint_errors = validate_with_helm_lint(chart_path, default_values)
        result["lint_valid"] = lint_valid
        if not lint_valid:
            result["valid"] = False
            result["errors"].extend([f"Lint: {e}" for e in lint_errors])
            print(f"❌")
            for err in lint_errors[:3]:
                print(f"      {err[:100]}")
        else:
            print("✓")
        
        # Return the fixed values in result if fix mode
        if fix and result["fixed"]:
            result["fixed_values"] = default_values
    
    return result


def save_definition(path: Path, definition: Dict[str, Any]):
    """Save a component definition YAML file."""
    with open(path, 'w') as f:
        yaml.dump(definition, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def update_version_in_file(path: Path, old_version: str, new_version: str) -> bool:
    """Update version in file preserving formatting."""
    try:
        content = path.read_text()
        # Replace version string
        new_content = re.sub(
            rf'(version:\s*["\']?){re.escape(old_version)}(["\']?)',
            rf'\g<1>{new_version}\g<2>',
            content
        )
        if new_content != content:
            path.write_text(new_content)
            return True
    except Exception as e:
        print(f"Error updating {path}: {e}", file=sys.stderr)
    return False


def check_all_versions(update: bool = False, component_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Check all component versions and optionally update them."""
    results = []
    
    if not DEFINITIONS_DIR.exists():
        print(f"Error: Definitions directory not found: {DEFINITIONS_DIR}", file=sys.stderr)
        return results
    
    for yaml_file in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        definition = load_definition(yaml_file)
        if not definition:
            continue
        
        component_id = definition.get("id", yaml_file.stem)
        
        # Filter by component if specified
        if component_filter and component_filter not in component_id:
            continue
        
        # Support both "upstream" (new style) and "helm" (old style)
        upstream_config = definition.get("upstream", {}) or definition.get("helm", {})
        current_version = upstream_config.get("version")
        
        if not current_version:
            continue
        
        print(f"Checking {component_id}...", end=" ", flush=True)
        latest_version = get_latest_version(upstream_config)
        
        result = {
            "id": component_id,
            "file": str(yaml_file.name),
            "current": current_version,
            "latest": latest_version,
            "needs_update": False,
            "updated": False
        }
        
        if latest_version:
            if current_version != latest_version:
                result["needs_update"] = True
                print(f"⬆️  {current_version} → {latest_version}")
                
                if update:
                    if update_version_in_file(yaml_file, current_version, latest_version):
                        result["updated"] = True
                        print(f"  ✅ Updated {yaml_file.name}")
            else:
                print(f"✓ {current_version} (up to date)")
        else:
            print(f"? {current_version} (couldn't fetch latest)")
        
        results.append(result)
    
    return results


def validate_all_components(component_filter: Optional[str] = None, fix: bool = False) -> List[Dict[str, Any]]:
    """Validate all components' defaultValues against their charts."""
    results = []
    
    if not DEFINITIONS_DIR.exists():
        print(f"Error: Definitions directory not found: {DEFINITIONS_DIR}", file=sys.stderr)
        return results
    
    for yaml_file in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        definition = load_definition(yaml_file)
        if not definition:
            continue
        
        component_id = definition.get("id", yaml_file.stem)
        
        # Filter by component if specified
        if component_filter and component_filter not in component_id:
            continue
        
        # Skip components without upstream config
        upstream_config = definition.get("upstream", {}) or definition.get("helm", {})
        if not upstream_config.get("repository"):
            continue
        
        print(f"\n{'='*60}")
        print(f"📦 {'Fixing' if fix else 'Validating'}: {component_id}")
        print(f"{'='*60}")
        
        result = validate_component(definition, component_id, fix=fix)
        result["file"] = str(yaml_file.name)
        
        # If fixed, update the definition file
        if fix and result.get("fixed") and result.get("fixed_values") is not None:
            print(f"  💾 Saving fixed values...", end=" ", flush=True)
            try:
                # Read original file to preserve comments/formatting
                content = yaml_file.read_text()
                
                # Update defaultValues section
                definition["defaultValues"] = result["fixed_values"]
                save_definition(yaml_file, definition)
                print("✓")
                
                # Re-validate after fix
                print(f"  🔄 Re-validating after fix...")
                revalidate = validate_component(definition, component_id, fix=False)
                result["valid"] = revalidate["valid"]
                result["errors"] = revalidate["errors"]
                if revalidate["valid"]:
                    print(f"  ✅ Now valid!")
                else:
                    print(f"  ⚠️  Still has errors after fix")
            except Exception as e:
                print(f"❌ {e}")
        
        results.append(result)
    
    return results


def show_architecture() -> None:
    """Show component architecture - operators and their instances."""
    categories = load_categories()
    
    print("=" * 60)
    print("Component Architecture")
    print("=" * 60)
    print()
    
    # Load all definitions
    components = {}
    for yaml_file in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        definition = load_definition(yaml_file)
        if definition:
            components[definition.get("id", yaml_file.stem)] = definition
    
    # Group by category
    by_category: Dict[str, List[Dict]] = {}
    for comp_id, comp in components.items():
        cat = comp.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(comp)
    
    # Show by category with priority
    sorted_cats = sorted(by_category.keys(), key=lambda c: categories.get(c, {}).get("priority", 100))
    
    for cat in sorted_cats:
        cat_info = categories.get(cat, {"name": cat.title(), "icon": "📦"})
        comps = by_category[cat]
        
        print(f"\n{cat_info.get('icon', '📦')} {cat_info.get('name', cat)} ({len(comps)} components)")
        print("-" * 40)
        
        # Sort: operators first, then instances, then others
        operators = [c for c in comps if c.get("isOperator")]
        instances = [c for c in comps if c.get("multiInstance")]
        others = [c for c in comps if not c.get("isOperator") and not c.get("multiInstance")]
        
        # Show operators with their instances
        for op in operators:
            op_id = op.get("id")
            print(f"  🎛️  {op_id} (operator)")
            
            # Find instances for this operator
            op_instances = [i for i in instances if i.get("requiresOperator") == op_id]
            for inst in op_instances:
                print(f"      └─ 📦 {inst.get('id')} (multi-instance)")
        
        # Show standalone instances (no operator found in our definitions)
        orphan_instances = [i for i in instances if i.get("requiresOperator") not in [o.get("id") for o in operators]]
        for inst in orphan_instances:
            req = inst.get("requiresOperator", "unknown")
            print(f"  📦 {inst.get('id')} (requires: {req})")
        
        # Show regular components
        for comp in others:
            hidden = "👁️" if comp.get("hidden") else ""
            print(f"  📦 {comp.get('id')} {hidden}")
    
    print()
    print("=" * 60)
    print("Legend: 🎛️ = operator, 📦 = component, 👁️ = hidden")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Update Helm chart versions and validate component definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Check versions only
  %(prog)s --update                 # Update versions + auto-validate + auto-fix
  %(prog)s --validate               # Validate all components
  %(prog)s --fix                    # Fix invalid values
  %(prog)s --validate -c cert       # Validate components matching 'cert'
  %(prog)s --architecture           # Show component architecture
"""
    )
    parser.add_argument("--update", "-u", action="store_true", 
                        help="Update versions, then auto-validate and auto-fix")
    parser.add_argument("--validate", "-v", action="store_true", 
                        help="Validate defaultValues against chart schemas")
    parser.add_argument("--fix", "-f", action="store_true", 
                        help="Fix invalid values (remove disallowed properties)")
    parser.add_argument("--component", "-c", type=str, 
                        help="Filter by component ID (partial match)")
    parser.add_argument("--json", "-j", action="store_true", 
                        help="Output as JSON")
    parser.add_argument("--architecture", "-a", action="store_true",
                        help="Show component architecture (operators/instances)")
    args = parser.parse_args()
    
    # Architecture mode
    if args.architecture:
        show_architecture()
        return
    
    # Fix mode
    if args.fix:
        print("=" * 60)
        print("Fixing component defaultValues...")
        print("=" * 60)
        
        results = validate_all_components(component_filter=args.component, fix=True)
        
        if args.json:
            print(json.dumps(results, indent=2))
            return
        
        # Summary
        print()
        print("=" * 60)
        print("Fix Summary")
        print("=" * 60)
        
        fixed = [r for r in results if r.get("fixed")]
        still_invalid = [r for r in results if not r["valid"]]
        
        print(f"Total processed: {len(results)}")
        print(f"🔧 Fixed: {len(fixed)}")
        print(f"✅ Now valid: {len(results) - len(still_invalid)}")
        print(f"❌ Still invalid: {len(still_invalid)}")
        
        if fixed:
            print("\n🔧 Fixed components:")
            for r in fixed:
                print(f"  📦 {r['id']}:")
                for prop in r.get("removed_properties", []):
                    print(f"      ❌ Removed: {prop}")
                for prop in r.get("added_properties", []):
                    print(f"      ✅ Added: {prop}")
        
        if still_invalid:
            print("\n❌ Components still with errors (may need manual fix):")
            for r in still_invalid:
                print(f"  📦 {r['id']}:")
                for err in r["errors"][:3]:
                    print(f"      - {err[:100]}")
            sys.exit(1)
        
        return
    
    # Validation mode
    if args.validate:
        print("=" * 60)
        print("Validating component defaultValues against chart schemas...")
        print("=" * 60)
        
        results = validate_all_components(component_filter=args.component, fix=False)
        
        if args.json:
            print(json.dumps(results, indent=2))
            return
        
        # Summary
        print()
        print("=" * 60)
        print("Validation Summary")
        print("=" * 60)
        
        valid = [r for r in results if r["valid"]]
        invalid = [r for r in results if not r["valid"]]
        
        print(f"Total validated: {len(results)}")
        print(f"✅ Valid: {len(valid)}")
        print(f"❌ Invalid: {len(invalid)}")
        
        if invalid:
            print("\n❌ Components with validation errors:")
            for r in invalid:
                print(f"\n  📦 {r['id']}:")
                for err in r["errors"][:5]:
                    print(f"      - {err[:100]}")
            
            print("\n💡 Run with --fix to auto-fix invalid values")
            sys.exit(1)
        else:
            print("\n✅ All components validated successfully!")
        
        return
    
    # Version check/update mode (default)
    print("=" * 60)
    print("Checking Helm chart versions...")
    print("=" * 60)
    print()
    
    results = check_all_versions(update=args.update, component_filter=args.component)
    
    if args.json:
        print(json.dumps(results, indent=2))
        return
    
    # Summary
    print()
    print("=" * 60)
    print("Version Summary")
    print("=" * 60)
    
    needs_update = [r for r in results if r["needs_update"]]
    updated = [r for r in results if r["updated"]]
    unknown = [r for r in results if r["latest"] is None]
    
    print(f"Total components: {len(results)}")
    print(f"Up to date: {len(results) - len(needs_update) - len(unknown)}")
    print(f"Needs update: {len(needs_update)}")
    print(f"Unknown: {len(unknown)}")
    
    if updated:
        print(f"\n✅ Updated {len(updated)} component(s)")
        
        # Auto-validate and fix after update
        print()
        print("=" * 60)
        print("Auto-validating updated components...")
        print("=" * 60)
        
        # Get list of updated component IDs
        updated_ids = [r["id"] for r in updated]
        
        validation_results = []
        for uid in updated_ids:
            vresults = validate_all_components(component_filter=uid, fix=True)
            validation_results.extend(vresults)
        
        still_invalid = [r for r in validation_results if not r["valid"]]
        if still_invalid:
            print(f"\n⚠️  {len(still_invalid)} component(s) still have validation errors after auto-fix")
            print("   Manual intervention may be required")
        else:
            print(f"\n✅ All {len(updated)} updated component(s) validated successfully!")
    
    if needs_update and not args.update:
        print("\n💡 Run with --update to update definition files")
    
    if unknown:
        print("\n⚠️  Could not fetch versions for:")
        for r in unknown:
            print(f"  - {r['id']}")


if __name__ == "__main__":
    main()
