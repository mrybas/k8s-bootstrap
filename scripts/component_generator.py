#!/usr/bin/env python3
"""
Component Definition Generator
==============================

Generates component definition YAML files from Helm charts.
Runs inside Docker via add-component.sh - no local dependencies needed.

Usage:
    # Interactive mode (recommended)
    make add-component
    
    # With arguments via wrapper script
    ./scripts/add-component.sh --id external-dns --repo https://... --chart external-dns
    
    # Direct Python execution (requires local dependencies: pyyaml, helm)
    python scripts/component_generator.py --id external-dns --repo https://... --chart external-dns
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# ============================================================================
# Category Management
# ============================================================================

def load_categories(definitions_path: Path) -> Dict[str, Dict]:
    """Load categories from definitions/categories.yaml"""
    categories_file = definitions_path / "categories.yaml"
    
    if categories_file.exists():
        with open(categories_file) as f:
            data = yaml.safe_load(f)
            return data.get("categories", {})
    
    # Fallback defaults if file not found
    return {
        "apps": {"name": "Apps", "icon": "📦", "description": "Application deployments"}
    }


def get_definitions_path() -> Path:
    """Get path to definitions directory."""
    # Check common locations
    paths = [
        Path("/app/backend/definitions"),  # Docker mount
        Path("backend/definitions"),        # Project root
        Path("../backend/definitions"),     # From scripts dir
    ]
    
    for p in paths:
        if p.exists():
            return p
    
    # Default
    return Path("backend/definitions")


# ============================================================================
# Icon and Category Guessing
# ============================================================================

# Keywords to icon mapping
ICON_HINTS = {
    "ingress": "🌐", "nginx": "🌐", "traefik": "🌐", "gateway": "🌐",
    "cert": "🔐", "secret": "🔐", "vault": "🔐", "sealed": "🔐", "oauth": "🔐",
    "prometheus": "📊", "grafana": "📊", "loki": "📊", "monitor": "📊",
    "metrics": "📈", "alert": "🚨", "victoria": "📈",
    "storage": "💾", "longhorn": "💾", "velero": "💾", "backup": "💾", "ceph": "💾", "rook": "💾",
    "dns": "🌍", "external-dns": "🌍",
    "flux": "🔄", "argo": "🔄", "gitops": "🔄",
    "autoscaler": "📈", "metal": "🔧",
    "core": "⚙️", "system": "⚙️", "operator": "🎛️",
    "instance": "📦", "cluster": "🔷",
}

# Keywords for detecting operators (will set isOperator: true)
OPERATOR_KEYWORDS = ["operator", "-operator"]

# Keywords for detecting instances (will set multiInstance: true)
INSTANCE_KEYWORDS = ["instance", "cluster", "single"]

# Operator to instance mappings
OPERATOR_INSTANCE_MAP = {
    "grafana-operator": ["grafana-instance"],
    "victoria-metrics-operator": ["victoria-metrics-single", "victoria-metrics-cluster"],
    "rook-ceph-operator": ["rook-ceph-cluster"],
    "prometheus-operator": ["prometheus-instance"],
}

# Keywords to category mapping
CATEGORY_HINTS = {
    "ingress": ["ingress", "nginx", "traefik", "gateway", "load balancer"],
    "security": ["cert", "secret", "vault", "seal", "auth", "oauth", "security"],
    "observability": ["prometheus", "grafana", "loki", "monitor", "metric", "trace", "log", "alert", "victoria"],
    "storage": ["storage", "longhorn", "velero", "backup", "pv", "volume"],
    "gitops": ["flux", "argo", "gitops"],
    "system": ["dns", "core", "system", "autoscal", "metal", "coredns"],
}


def guess_icon(name: str, categories: Dict) -> str:
    """Guess icon based on component name."""
    name_lower = name.lower()
    
    for keyword, icon in ICON_HINTS.items():
        if keyword in name_lower:
            return icon
    
    return "📦"


def guess_category(name: str, description: str, categories: Dict) -> str:
    """Guess category based on component name and description."""
    text = f"{name} {description}".lower()
    
    for category, keywords in CATEGORY_HINTS.items():
        if category in categories:  # Only suggest existing categories
            if any(k in text for k in keywords):
                return category
    
    return "apps"


# ============================================================================
# Helm Chart Fetching
# ============================================================================

def fetch_chart_info(repo_url: str, chart_name: str, version: Optional[str] = None) -> Dict[str, Any]:
    """Fetch chart information using helm."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_name = "temp-repo"
        try:
            # Handle OCI registries
            if repo_url.startswith("oci://"):
                chart_ref = f"{repo_url}/{chart_name}"
                cmd = ["helm", "show", "all", chart_ref]
                if version:
                    cmd.extend(["--version", version])
            else:
                # Add traditional repo
                subprocess.run(
                    ["helm", "repo", "add", repo_name, repo_url],
                    capture_output=True, check=True
                )
                subprocess.run(["helm", "repo", "update"], capture_output=True, check=True)
                
                chart_ref = f"{repo_name}/{chart_name}"
                cmd = ["helm", "show", "all", chart_ref]
                if version:
                    cmd.extend(["--version", version])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse output (Chart.yaml + values.yaml separated by ---)
            parts = result.stdout.split("---")
            chart_yaml = {}
            values_yaml = {}
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                try:
                    parsed = yaml.safe_load(part)
                    if parsed:
                        if "apiVersion" in parsed or ("name" in parsed and "version" in parsed):
                            chart_yaml = parsed
                        else:
                            values_yaml = parsed
                except Exception:
                    pass
            
            return {"chart": chart_yaml, "values": values_yaml}
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Helm error: {e.stderr}")
            return {"chart": {}, "values": {}}
        finally:
            if not repo_url.startswith("oci://"):
                subprocess.run(["helm", "repo", "remove", repo_name], capture_output=True)


# ============================================================================
# Schema Generation
# ============================================================================

def infer_schema_type(value: Any) -> Dict[str, Any]:
    """Infer JSON schema type from a Python value."""
    if value is None:
        return {"type": "string"}
    elif isinstance(value, bool):
        return {"type": "boolean", "default": value}
    elif isinstance(value, int):
        return {"type": "integer", "default": value}
    elif isinstance(value, float):
        return {"type": "number", "default": value}
    elif isinstance(value, str):
        return {"type": "string", "default": value}
    elif isinstance(value, list):
        if value:
            item_schema = infer_schema_type(value[0])
            return {"type": "array", "items": item_schema, "default": value}
        return {"type": "array", "items": {"type": "string"}, "default": []}
    elif isinstance(value, dict):
        if not value:
            return {"type": "object", "additionalProperties": True}
        properties = {}
        for k, v in value.items():
            properties[k] = infer_schema_type(v)
        return {"type": "object", "properties": properties}
    return {"type": "string"}


def generate_json_schema(values: Dict[str, Any], max_depth: int = 2) -> Dict[str, Any]:
    """Generate simplified JSON schema from Helm values."""
    # Priority keys to include
    priority_keys = [
        "enabled", "replicaCount", "replicas", "image", "service", 
        "resources", "persistence", "ingress", "config", "args"
    ]
    
    schema = {"type": "object", "properties": {}}
    
    for key in priority_keys:
        if key in values:
            prop = infer_schema_type(values[key])
            prop["title"] = key.replace("_", " ").title()
            schema["properties"][key] = prop
    
    # Always add resources
    if "resources" not in schema["properties"]:
        schema["properties"]["resources"] = {
            "type": "object",
            "title": "Resources",
            "properties": {
                "requests": {
                    "type": "object",
                    "properties": {
                        "cpu": {"type": "string", "title": "CPU Request", "default": "100m"},
                        "memory": {"type": "string", "title": "Memory Request", "default": "128Mi"}
                    }
                },
                "limits": {
                    "type": "object",
                    "properties": {
                        "cpu": {"type": "string", "title": "CPU Limit", "default": "500m"},
                        "memory": {"type": "string", "title": "Memory Limit", "default": "512Mi"}
                    }
                }
            }
        }
    
    return schema


def generate_ui_schema(json_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Generate UI schema hints."""
    ui_schema = {}
    
    for key, prop in json_schema.get("properties", {}).items():
        prop_type = prop.get("type")
        
        if prop_type == "integer":
            ui_schema[key] = {"ui:widget": "updown"}
        elif prop_type == "object" and key in ["resources", "affinity", "tolerations"]:
            ui_schema[key] = {"ui:collapsed": True}
        elif prop_type == "array":
            ui_schema[key] = {"ui:widget": "array"}
        elif "enum" in prop:
            ui_schema[key] = {"ui:widget": "select"}
    
    return ui_schema


# ============================================================================
# Component Definition Generation
# ============================================================================

def detect_component_type(component_id: str) -> Dict[str, Any]:
    """Detect if component is an operator or multi-instance."""
    result = {
        "isOperator": False,
        "multiInstance": False,
        "requiresOperator": None,
    }
    
    id_lower = component_id.lower()
    
    # Check if it's an operator
    for keyword in OPERATOR_KEYWORDS:
        if keyword in id_lower:
            result["isOperator"] = True
            break
    
    # Check if it's a multi-instance component
    if not result["isOperator"]:
        for keyword in INSTANCE_KEYWORDS:
            if keyword in id_lower:
                result["multiInstance"] = True
                break
    
    # Find the operator this instance requires
    if result["multiInstance"]:
        for operator, instances in OPERATOR_INSTANCE_MAP.items():
            # Check if component matches any known instance pattern
            operator_base = operator.replace("-operator", "")
            if operator_base in id_lower:
                result["requiresOperator"] = operator
                break
    
    return result


def generate_component_yaml(
    component_id: str,
    repo_url: str,
    chart_name: str,
    version: str,
    category: str,
    categories: Dict,
    name: Optional[str] = None,
    description: Optional[str] = None,
    namespace: Optional[str] = None,
    icon: Optional[str] = None,
    docs_url: Optional[str] = None,
    fetch_values: bool = True,
    is_operator: bool = False,
    multi_instance: bool = False,
    requires_operator: Optional[str] = None
) -> str:
    """Generate complete component definition YAML."""
    
    # Fetch chart info
    chart_info = {"chart": {}, "values": {}}
    if fetch_values:
        print(f"📥 Fetching chart info from {repo_url}...")
        chart_info = fetch_chart_info(repo_url, chart_name, version)
        
        chart_meta = chart_info.get("chart", {})
        if not name:
            name = chart_meta.get("name", chart_name).replace("-", " ").title()
        if not description:
            description = chart_meta.get("description", f"{name} Helm chart")
        if not version or version == "latest":
            version = chart_meta.get("version", version)
    
    # Apply defaults
    name = name or chart_name.replace("-", " ").title()
    description = description or f"{name} Helm chart"
    namespace = namespace or component_id
    icon = icon or guess_icon(component_id, categories)
    
    cat_info = categories.get(category, {"name": category.title(), "description": "", "icon": "📦"})
    app_version = chart_info.get("chart", {}).get("appVersion", version)
    
    # Generate schemas
    values = chart_info.get("values", {})
    json_schema = generate_json_schema(values) if values else {
        "type": "object",
        "properties": {
            "replicaCount": {"type": "integer", "title": "Replicas", "minimum": 1, "default": 1}
        }
    }
    ui_schema = generate_ui_schema(json_schema)
    
    # Extract useful defaults
    default_values = {}
    for key in ["replicaCount", "replicas", "enabled"]:
        if key in values:
            default_values[key] = values[key]
    if not default_values:
        default_values["replicaCount"] = 1
    
    # Detect component type if not specified
    comp_type = detect_component_type(component_id)
    is_operator = is_operator or comp_type["isOperator"]
    multi_instance = multi_instance or comp_type["multiInstance"]
    requires_operator = requires_operator or comp_type["requiresOperator"]
    
    # Build YAML
    lines = [
        f"# {name} Component Definition",
        "# Auto-generated - review and customize as needed",
        "",
        f"id: {component_id}",
        f"name: {name}",
        f"description: {description}",
        f"category: {category}",
        f"categoryName: {cat_info.get('name', category.title())}",
        f"categoryDescription: {cat_info.get('description', '')}",
        f'icon: "{icon}"',
        "priority: 50",
        f"docsUrl: {docs_url or ''}",
    ]
    
    # Add operator/instance flags
    if is_operator:
        lines.extend([
            "",
            "# This is an operator that manages instances",
            "isOperator: true",
        ])
    
    if multi_instance:
        lines.extend([
            "",
            "# Multi-instance - can deploy multiple instances in different namespaces",
            "multiInstance: true",
        ])
        if requires_operator:
            lines.append(f"requiresOperator: {requires_operator}")
    
    lines.extend([
        "",
        "chartType: upstream",
        f"namespace: {namespace}",
        f"releaseName: {component_id}",
        "createNamespace: true",
        "timeout: 5m",
        "",
        "# Upstream chart details",
        "upstream:",
        f"  repository: {repo_url}",
        f"  chartName: {chart_name}",
        f'  version: "{version}"',
        f'  appVersion: "{app_version}"',
        "",
        "# Dependencies",
        "dependsOn:",
    ])
    
    # Add proper dependencies
    if requires_operator:
        lines.append(f"  - {requires_operator}")
    lines.append("  - namespaces")
    
    lines.extend([
        "",
        "# Default values",
        "defaultValues:",
    ])
    
    for k, v in default_values.items():
        if isinstance(v, (dict, list)):
            lines.append(f"  {k}: {json.dumps(v)}")
        else:
            lines.append(f"  {k}: {v}")
    
    lines.extend(["", "# JSON Schema for UI form", "jsonSchema:"])
    for line in yaml.dump(json_schema, default_flow_style=False, allow_unicode=True).split("\n"):
        if line:
            lines.append(f"  {line}")
    
    lines.extend(["", "# UI Schema", "uiSchema:"])
    for line in yaml.dump(ui_schema, default_flow_style=False, allow_unicode=True).split("\n"):
        if line:
            lines.append(f"  {line}")
    
    return "\n".join(lines)


# ============================================================================
# Interactive Mode
# ============================================================================

def interactive_mode(categories: Dict, definitions_path: Path):
    """Run interactive mode."""
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         Component Definition Generator                       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    
    # Component ID
    component_id = input("Component ID (e.g., external-dns): ").strip()
    if not component_id:
        print("❌ Component ID is required")
        sys.exit(1)
    
    output_path = definitions_path / "components" / f"{component_id}.yaml"
    if output_path.exists():
        overwrite = input(f"⚠️  {output_path} exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Cancelled")
            sys.exit(0)
    
    # Repository
    repo_url = input("Helm repository URL: ").strip()
    if not repo_url:
        print("❌ Repository URL is required")
        sys.exit(1)
    
    chart_name = input(f"Chart name [{component_id}]: ").strip() or component_id
    version = input("Chart version (leave empty for latest): ").strip() or "latest"
    
    # Category
    print()
    print("Available categories:")
    for key, info in categories.items():
        print(f"  {key:15} - {info.get('icon', '📦')} {info.get('name', key)}")
    print()
    print("  (or type a new category name to create it)")
    
    default_cat = guess_category(component_id, "", categories)
    category = input(f"Category [{default_cat}]: ").strip() or default_cat
    
    # Check if new category
    if category not in categories:
        print(f"\n📝 New category '{category}' will be created")
        cat_name = input(f"  Display name [{category.title()}]: ").strip() or category.title()
        cat_icon = input("  Icon [📦]: ").strip() or "📦"
        cat_desc = input("  Description: ").strip() or f"{cat_name} components"
        
        # Add to categories file
        categories[category] = {"name": cat_name, "icon": cat_icon, "description": cat_desc}
        save_categories(categories, definitions_path)
        print(f"  ✅ Category '{category}' added to categories.yaml")
    
    # Optional fields
    name = input(f"Display name [{chart_name.replace('-', ' ').title()}]: ").strip()
    namespace = input(f"Namespace [{component_id}]: ").strip()
    docs_url = input("Documentation URL: ").strip()
    
    # Detect component type
    comp_type = detect_component_type(component_id)
    
    print()
    print("Component Type Detection:")
    if comp_type["isOperator"]:
        print(f"  ✓ Detected as OPERATOR")
    elif comp_type["multiInstance"]:
        print(f"  ✓ Detected as MULTI-INSTANCE component")
        if comp_type["requiresOperator"]:
            print(f"    Requires operator: {comp_type['requiresOperator']}")
    
    # Allow override
    is_operator = comp_type["isOperator"]
    multi_instance = comp_type["multiInstance"]
    requires_operator = comp_type["requiresOperator"]
    
    override = input("\nOverride detection? [y/N]: ").strip().lower()
    if override == "y":
        is_op = input("  Is this an operator? [y/N]: ").strip().lower()
        is_operator = is_op == "y"
        
        if not is_operator:
            is_multi = input("  Is this a multi-instance component? [y/N]: ").strip().lower()
            multi_instance = is_multi == "y"
            
            if multi_instance:
                requires_operator = input("  Requires operator (e.g., grafana-operator): ").strip() or None
    
    fetch = input("\nFetch chart values for schema generation? [Y/n]: ").strip().lower()
    fetch_values = fetch != "n"
    
    print("\n🔧 Generating component definition...")
    
    definition = generate_component_yaml(
        component_id=component_id,
        repo_url=repo_url,
        chart_name=chart_name,
        version=version,
        category=category,
        categories=categories,
        name=name or None,
        namespace=namespace or None,
        docs_url=docs_url or None,
        fetch_values=fetch_values,
        is_operator=is_operator,
        multi_instance=multi_instance,
        requires_operator=requires_operator
    )
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(definition)
    
    print()
    print(f"✅ Created: {output_path}")
    print()
    print("Next steps:")
    print(f"  1. Review and edit: {output_path}")
    print(f"  2. Test: make validate-component COMPONENT={component_id}")
    print()


def save_categories(categories: Dict, definitions_path: Path):
    """Save categories to file."""
    categories_file = definitions_path / "categories.yaml"
    
    content = {
        "categories": categories
    }
    
    with open(categories_file, "w") as f:
        f.write("# Component Categories\n")
        f.write("# Add new categories here\n\n")
        yaml.dump(content, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate component definition from Helm chart",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("--id", help="Component ID")
    parser.add_argument("--repo", help="Helm repository URL")
    parser.add_argument("--chart", help="Chart name")
    parser.add_argument("--version", default="latest", help="Chart version")
    parser.add_argument("--category", help="Component category")
    parser.add_argument("--name", help="Display name")
    parser.add_argument("--namespace", help="Kubernetes namespace")
    parser.add_argument("--docs-url", help="Documentation URL")
    parser.add_argument("--no-fetch", action="store_true", help="Don't fetch chart values")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--print", action="store_true", dest="print_output", help="Print to stdout")
    parser.add_argument("--list-categories", action="store_true", help="List available categories")
    parser.add_argument("--operator", action="store_true", help="Mark as operator component")
    parser.add_argument("--multi-instance", action="store_true", help="Mark as multi-instance component")
    parser.add_argument("--requires-operator", help="Operator this instance requires")
    
    args = parser.parse_args()
    
    definitions_path = get_definitions_path()
    categories = load_categories(definitions_path)
    
    # List categories
    if args.list_categories:
        print("Available categories:")
        for key, info in categories.items():
            print(f"  {key:15} - {info.get('icon', '📦')} {info.get('name', key)}")
        sys.exit(0)
    
    # Interactive mode
    if not args.id or not args.repo:
        interactive_mode(categories, definitions_path)
        return
    
    # CLI mode
    category = args.category or guess_category(args.id, "", categories)
    
    definition = generate_component_yaml(
        component_id=args.id,
        repo_url=args.repo,
        chart_name=args.chart or args.id,
        version=args.version,
        category=category,
        categories=categories,
        name=args.name,
        namespace=args.namespace,
        docs_url=args.docs_url,
        fetch_values=not args.no_fetch,
        is_operator=args.operator,
        multi_instance=args.multi_instance,
        requires_operator=args.requires_operator
    )
    
    if args.print_output:
        print(definition)
    else:
        output_path = Path(args.output) if args.output else definitions_path / "components" / f"{args.id}.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(definition)
        print(f"✅ Created: {output_path}")


if __name__ == "__main__":
    main()
