"""
K8s Bootstrap - FastAPI Backend
Generates GitOps bootstrap repositories for Kubernetes clusters
"""
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.definitions import DefinitionLoader
from app.core.storage import get_storage
from app.generator.repo_generator import RepoGenerator
from app.generator.chart_generator import ChartGenerator
from app.generator.bootstrap_generator import GitAuthConfig as BootstrapGitAuthConfig
from app.generator.update_generator import UpdateGenerator, calculate_file_checksum

app = FastAPI(
    title="K8s Bootstrap",
    description="Generate GitOps bootstrap repositories for Kubernetes",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize definition loader
definition_loader = DefinitionLoader(settings.definitions_path)


class ComponentInstance(BaseModel):
    """Instance configuration for multi-instance components"""
    name: str
    namespace: str
    values: Dict[str, Any] = {}
    raw_overrides: str = ""


class ComponentSelection(BaseModel):
    """Component selection with values"""
    id: str
    enabled: bool = True
    values: Dict[str, Any] = {}
    raw_overrides: str = ""
    # For multi-instance components
    instances: Optional[List[ComponentInstance]] = None


class GitAuthConfig(BaseModel):
    """Git authentication configuration for private repositories"""
    enabled: bool = False
    platform: str = "github"  # github, gitlab, gitea
    customUrl: Optional[str] = None  # For self-hosted GitLab/Gitea


class GenerateRequest(BaseModel):
    """Request to generate bootstrap package"""
    cluster_name: str
    repo_url: str
    branch: str = "main"
    components: List[ComponentSelection]
    git_auth: Optional[GitAuthConfig] = None
    skip_git_push: bool = False  # If true, don't push to remote (local preview mode)


class BootstrapCreateResponse(BaseModel):
    """Response from bootstrap creation"""
    token: str
    curl_command: str
    expires_in_minutes: int
    one_time: bool


class UpdateCreateResponse(BaseModel):
    """Response from update creation"""
    token: str
    curl_command: str
    expires_in_minutes: int
    one_time: bool
    files_count: int
    charts_count: int


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# Documentation endpoints
# In Docker: mounted at /app/docs, in dev: two levels up from backend/app/
DOCS_PATH = Path("/app/docs") if Path("/app/docs").exists() else Path(__file__).parent.parent.parent / "docs"

@app.get("/api/docs")
async def list_docs():
    """List available documentation files"""
    if not DOCS_PATH.exists():
        return {"docs": []}
    
    docs = []
    for f in sorted(DOCS_PATH.glob("*.md")):
        docs.append({
            "id": f.stem,
            "filename": f.name
        })
    return {"docs": docs}


@app.get("/api/docs/{doc_id}")
async def get_doc(doc_id: str):
    """Get documentation content by ID"""
    # Security: only allow alphanumeric and hyphens
    if not doc_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid document ID")
    
    doc_path = DOCS_PATH / f"{doc_id}.md"
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    content = doc_path.read_text(encoding="utf-8")
    return {"id": doc_id, "content": content}


@app.get("/api/categories")
async def get_categories():
    """Get all component categories (excluding hidden components)"""
    definitions = definition_loader.load_all()
    category_defs = definition_loader.load_categories()
    categories = {}
    
    for comp in definitions.values():
        # Skip hidden components (like namespaces which is auto-generated)
        if comp.get("hidden", False):
            continue
            
        cat = comp.get("category", "other")
        if cat not in categories:
            # Use category definition if available, otherwise fallback to component metadata
            cat_def = category_defs.get(cat, {})
            categories[cat] = {
                "id": cat,
                "name": cat_def.get("name", comp.get("categoryName", cat.title())),
                "description": cat_def.get("description", comp.get("categoryDescription", "")),
                "icon": cat_def.get("icon", "📦"),
                "priority": cat_def.get("priority", 100),
                "components": []
            }
        
        # Build component info with new fields
        comp_info = {
            "id": comp["id"],
            "name": comp["name"],
            "description": comp["description"],
            "icon": comp.get("icon", ""),
            "version": comp.get("upstream", {}).get("version", ""),
            "hasConfig": bool(comp.get("jsonSchema")),
            "docsUrl": comp.get("docsUrl", ""),
            # Operator pattern support
            "isOperator": comp.get("isOperator", False),
            "operatorFor": comp.get("operatorFor", ""),
            "suggestsInstances": comp.get("suggestsInstances", []),
            "suggestsComponents": comp.get("suggestsComponents", []),
            # Instance pattern support
            "isInstance": comp.get("isInstance", False),
            "instanceOf": comp.get("instanceOf", ""),
            # Multi-instance pattern support
            "multiInstance": comp.get("multiInstance", False),
            "defaultNamespace": comp.get("namespace", comp["id"]),
            "requiresOperator": comp.get("requiresOperator", ""),
        }
        categories[cat]["components"].append(comp_info)
    
    # Sort components by priority within each category
    for cat in categories.values():
        cat["components"].sort(
            key=lambda c: definitions.get(c["id"], {}).get("priority", 100)
        )
    
    # Sort categories by priority from categories.yaml
    result = [cat for cat in categories.values() if cat["components"]]
    result.sort(key=lambda c: c.get("priority", 100))
    
    return result


@app.get("/api/components")
async def get_components():
    """Get all available components (excluding hidden)"""
    definitions = definition_loader.load_all()
    result = []
    
    for comp in definitions.values():
        if comp.get("hidden", False):
            continue
        
        comp_info = dict(comp)
        comp_info["hasConfig"] = bool(comp.get("jsonSchema"))
        result.append(comp_info)
    
    return result


@app.get("/api/components/{component_id}")
async def get_component(component_id: str):
    """Get component definition with UI schema"""
    definitions = definition_loader.load_all()
    if component_id not in definitions:
        raise HTTPException(status_code=404, detail="Component not found")
    
    comp = definitions[component_id]
    return {
        **comp,
        "hasConfig": bool(comp.get("jsonSchema")),
    }


@app.get("/api/components/{component_id}/schema")
async def get_component_schema(component_id: str):
    """Get UI schema for component configuration form"""
    definitions = definition_loader.load_all()
    if component_id not in definitions:
        raise HTTPException(status_code=404, detail="Component not found")
    
    comp = definitions[component_id]
    return {
        "jsonSchema": comp.get("jsonSchema", {}),
        "uiSchema": comp.get("uiSchema", {}),
        "defaultValues": comp.get("defaultValues", {})
    }


def validate_instance_operators(
    selected_ids: Set[str],
    definitions: Dict[str, Any]
) -> List[str]:
    """
    Validate that all instance components have their operators selected.
    Returns list of validation error messages (empty if valid).
    """
    errors = []
    for comp_id in selected_ids:
        comp_def = definitions.get(comp_id, {})
        if comp_def.get("isInstance") and comp_def.get("instanceOf"):
            operator_id = comp_def["instanceOf"]
            if operator_id not in selected_ids:
                errors.append(
                    f"'{comp_def.get('name', comp_id)}' requires '{operator_id}' to be selected"
                )
    return errors


def resolve_dependencies(
    selected_ids: Set[str],
    definitions: Dict[str, Any]
) -> List[str]:
    """
    Resolve component dependencies and auto-includes.
    Returns ordered list of component IDs to install.
    """
    all_components: Set[str] = set(selected_ids)
    
    # Add always-included components (like flux)
    for comp_id, comp_def in definitions.items():
        if comp_def.get("alwaysInclude", False):
            all_components.add(comp_id)
    
    # Iteratively resolve dependencies
    changed = True
    while changed:
        changed = False
        for comp_id in list(all_components):
            comp_def = definitions.get(comp_id, {})
            
            # Add required CRDs
            if "requiresCrds" in comp_def:
                crds = comp_def["requiresCrds"]
                if isinstance(crds, str):
                    crds = [crds]
                for crd in crds:
                    if crd not in all_components and crd in definitions:
                        all_components.add(crd)
                        changed = True
            
            # Add dependencies
            for dep in comp_def.get("dependsOn", []):
                if dep not in all_components and dep in definitions:
                    all_components.add(dep)
                    changed = True
    
    # Check for auto-include components based on what's selected
    for comp_id, comp_def in definitions.items():
        if comp_id in all_components:
            continue
        
        auto_include = comp_def.get("autoInclude", {})
        when_components = auto_include.get("when", [])
        if when_components:
            # Include if any of the trigger components are selected
            if any(w in all_components for w in when_components):
                all_components.add(comp_id)
    
    # Sort by priority
    sorted_components = sorted(
        all_components,
        key=lambda cid: definitions.get(cid, {}).get("priority", 100)
    )
    
    return sorted_components


# ============================================================================
# Common Request Processing
# ============================================================================

def process_component_request(
    request: GenerateRequest,
    definitions: Dict[str, Any],
    validate_yaml: bool = True
) -> tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, "ComponentSelection"]]:
    """
    Process component selection from request.
    
    Common logic for both bootstrap and update endpoints:
    - Validates cluster name
    - Builds selection map  
    - Validates dependencies
    - Optionally validates raw YAML
    - Resolves dependencies
    - Builds component list
    
    Returns:
        (selected_components, helm_charts_info, user_selections)
    """
    # Validate cluster name
    if not request.cluster_name or not request.cluster_name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid cluster name")
    
    # Build selection map
    user_selections: Dict[str, ComponentSelection] = {}
    enabled_ids: Set[str] = set()
    
    for comp in request.components:
        if comp.enabled:
            user_selections[comp.id] = comp
            enabled_ids.add(comp.id)
    
    if not enabled_ids:
        raise HTTPException(status_code=400, detail="No components selected")
    
    # Validate instance/operator dependencies
    validation_errors = validate_instance_operators(enabled_ids, definitions)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid selection: {'; '.join(validation_errors)}"
        )
    
    # Validate raw YAML overrides (only for bootstrap, update skips this)
    if validate_yaml:
        yaml_errors = []
        for comp in request.components:
            if comp.enabled and comp.raw_overrides:
                is_valid, error_msg = ChartGenerator.validate_raw_yaml(comp.raw_overrides, comp.id)
                if not is_valid:
                    yaml_errors.append(error_msg)
        
        if yaml_errors:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid raw YAML: {'; '.join(yaml_errors)}"
            )
    
    # Resolve dependencies
    all_component_ids = resolve_dependencies(enabled_ids, definitions)
    
    # Build component list
    selected = []
    helm_charts_info = []
    
    for comp_id in all_component_ids:
        comp_def = definitions.get(comp_id)
        if not comp_def or comp_id == "namespaces":
            continue
        
        user_sel = user_selections.get(comp_id)
        
        # Handle multi-instance components
        if comp_def.get("multiInstance") and user_sel and user_sel.instances:
            for instance in user_sel.instances:
                # Create a modified definition for this instance
                instance_def = dict(comp_def)
                instance_def["_instance_name"] = instance.name
                instance_def["namespace"] = instance.namespace
                
                selected.append({
                    "definition": instance_def,
                    "values": instance.values,
                    "raw_overrides": instance.raw_overrides
                })
        else:
            # Single instance (default behavior)
            values = user_sel.values if user_sel else comp_def.get("defaultValues", {})
            raw_overrides = user_sel.raw_overrides if user_sel else ""
            
            selected.append({
                "definition": comp_def,
                "values": values,
                "raw_overrides": raw_overrides
            })
        
        # Collect chart info for helm pull commands
        # Skip meta-components (they don't have charts) and custom charts
        if comp_def.get("chartType") not in ("custom", "meta") and comp_def.get("upstream"):
            upstream = comp_def["upstream"]
            helm_charts_info.append({
                "id": comp_def["id"],
                "category": comp_def.get("category", "apps"),
                "name": upstream.get("chartName", comp_def["id"]),
                "version": upstream.get("version", "*"),
                "repository": upstream.get("repository", "")
            })
    
    return selected, helm_charts_info, user_selections


# ============================================================================
# Curl-based Bootstrap Endpoints
# ============================================================================

@app.post("/api/bootstrap", response_model=BootstrapCreateResponse)
async def create_bootstrap(request: GenerateRequest):
    """
    Create a bootstrap session and return a one-time curl command.
    
    The generated script uses `helm pull` to download charts at runtime,
    keeping the script size small and always fetching latest chart versions.
    """
    definitions = definition_loader.load_all()
    
    # Process request using common logic
    selected, helm_charts_info, _ = process_component_request(
        request, definitions, validate_yaml=True
    )
    
    # Generate repository
    temp_dir = tempfile.mkdtemp(prefix="k8s-bootstrap-")
    
    try:
        # Convert API git auth config to bootstrap generator config
        bootstrap_git_auth = None
        if request.git_auth and request.git_auth.enabled:
            bootstrap_git_auth = BootstrapGitAuthConfig(
                enabled=True,
                platform=request.git_auth.platform,
                custom_url=request.git_auth.customUrl
            )
        
        generator = RepoGenerator(
            output_dir=temp_dir,
            cluster_name=request.cluster_name,
            repo_url=request.repo_url,
            branch=request.branch,
            vendor_charts=False,  # Script contains helm pull commands
            git_auth=bootstrap_git_auth,
            skip_git_push=request.skip_git_push
        )
        
        repo_path = generator.generate(selected)
        
        # Store session
        storage = get_storage()
        session = storage.create_session(
            config={
                "cluster_name": request.cluster_name,
                "repo_url": request.repo_url,
                "branch": request.branch,
                "helm_charts": helm_charts_info
            },
            content_path=Path(repo_path),
            ttl_minutes=settings.session_ttl_minutes,
            one_time=True
        )
        
        # Generate curl command with relative path (frontend can prepend its own base URL)
        curl_cmd = f"curl -sSL /bootstrap/{session.token} | bash"
        
        return BootstrapCreateResponse(
            token=session.token,
            curl_command=curl_cmd,
            expires_in_minutes=settings.session_ttl_minutes,
            one_time=True
        )
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/bootstrap/{token}")
async def get_bootstrap_script(token: str):
    """
    Return a completely self-contained bootstrap script.
    
    The script contains ALL file contents embedded directly,
    no additional downloads required.
    Token is valid for one-time use only.
    """
    storage = get_storage()
    session = storage.get_session(token, mark_accessed=True)  # Mark as used
    
    if not session:
        return PlainTextResponse(
            content='#!/bin/bash\necho "Error: Invalid or expired bootstrap token"\nexit 1',
            media_type="text/plain",
            status_code=404
        )
    
    cluster_name = session.config.get("cluster_name", "k8s-cluster")
    repo_url = session.config.get("repo_url", "")
    branch = session.config.get("branch", "main")
    
    # Generate simple readable script with heredocs and helm pull
    script = generate_simple_script(
        content_path=session.content_path,
        cluster_name=cluster_name,
        repo_url=repo_url,
        branch=branch,
        helm_charts=session.config.get("helm_charts", [])
    )
    
    return PlainTextResponse(content=script, media_type="text/plain")


# ============================================================================
# Update Endpoints (for existing installations)
# ============================================================================

@app.post("/api/update", response_model=UpdateCreateResponse)
async def create_update(request: GenerateRequest):
    """
    Create an update session for existing installations.
    
    Unlike bootstrap, this generates an update script that:
    - Only updates changed files (compares checksums)
    - Skips charts with unchanged versions
    - Preserves git history
    - Triggers Flux reconciliation for changed components
    """
    definitions = definition_loader.load_all()
    
    # Process request using common logic (skip YAML validation for updates)
    selected, helm_charts_info, _ = process_component_request(
        request, definitions, validate_yaml=False
    )
    
    # Generate repository to get file contents
    temp_dir = tempfile.mkdtemp(prefix="k8s-bootstrap-update-")
    
    try:
        bootstrap_git_auth = None
        if request.git_auth and request.git_auth.enabled:
            bootstrap_git_auth = BootstrapGitAuthConfig(
                enabled=True,
                platform=request.git_auth.platform,
                custom_url=request.git_auth.customUrl
            )
        
        generator = RepoGenerator(
            output_dir=temp_dir,
            cluster_name=request.cluster_name,
            repo_url=request.repo_url,
            branch=request.branch,
            vendor_charts=False,
            git_auth=bootstrap_git_auth,
            skip_git_push=request.skip_git_push
        )
        
        repo_path = generator.generate(selected)
        
        # Collect files with checksums
        files_with_checksums = collect_files_with_checksums(repo_path)
        
        # Generate update script
        update_gen = UpdateGenerator(
            cluster_name=request.cluster_name,
            repo_url=request.repo_url,
            branch=request.branch,
            git_auth_enabled=request.git_auth.enabled if request.git_auth else False,
            git_platform=request.git_auth.platform if request.git_auth else "github"
        )
        
        update_script = update_gen.generate_update_script(
            new_files=files_with_checksums,
            helm_charts=helm_charts_info
        )
        
        # Store session with update script
        storage = get_storage()
        session = storage.create_session(
            config={
                "cluster_name": request.cluster_name,
                "repo_url": request.repo_url,
                "branch": request.branch,
                "is_update": True,
                "update_script": update_script,
            },
            content_path=Path(repo_path),
            ttl_minutes=settings.session_ttl_minutes,
            one_time=True
        )
        
        curl_cmd = f"curl -sSL /update/{session.token} | bash"
        
        return UpdateCreateResponse(
            token=session.token,
            curl_command=curl_cmd,
            expires_in_minutes=settings.session_ttl_minutes,
            one_time=True,
            files_count=len(files_with_checksums),
            charts_count=len(helm_charts_info)
        )
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/update/{token}")
async def get_update_script(token: str):
    """
    Return the update script for an existing installation.
    
    The script intelligently updates only changed files and charts.
    Token is valid for one-time use only.
    """
    storage = get_storage()
    session = storage.get_session(token, mark_accessed=True)
    
    if not session:
        return PlainTextResponse(
            content='#!/bin/bash\necho "Error: Invalid or expired update token"\nexit 1',
            media_type="text/plain",
            status_code=404
        )
    
    # Return the pre-generated update script
    update_script = session.config.get("update_script", "")
    if not update_script:
        return PlainTextResponse(
            content='#!/bin/bash\necho "Error: Update script not found"\nexit 1',
            media_type="text/plain",
            status_code=404
        )
    
    return PlainTextResponse(content=update_script, media_type="text/plain")


def collect_files_with_checksums(content_path: Path) -> List[Dict[str, Any]]:
    """
    Collect all files from content path with their checksums.
    Excludes vendored chart files (charts/*/charts/*).
    """
    files = []
    
    for root, dirs, filenames in os.walk(content_path):
        rel_root = Path(root).relative_to(content_path)
        
        for filename in filenames:
            file_path = Path(root) / filename
            rel_path = rel_root / filename
            
            # Skip vendored chart files
            parts = rel_path.parts
            if len(parts) >= 4 and parts[0] == "charts" and parts[2] == "charts":
                continue
            
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                continue
            
            # Check if executable
            is_executable = os.access(file_path, os.X_OK)
            
            files.append({
                'path': str(rel_path),
                'content': content,
                'checksum': calculate_file_checksum(content),
                'executable': is_executable
            })
    
    return files


def generate_simple_script(
    content_path: Path,
    cluster_name: str,
    repo_url: str,
    branch: str,
    helm_charts: List[Dict[str, str]] = None
) -> str:
    """
    Generate a simple, readable bash script.
    
    Uses:
    - mkdir for directories
    - cat << 'EOF' heredocs for file contents
    - helm repo add + helm pull for charts
    
    Args:
        helm_charts: List of charts to download via helm pull
                    Each dict has: id, name, version, repository
    """
    if helm_charts is None:
        helm_charts = []
    
    # Collect files (excluding vendored charts - we'll use helm pull instead)
    files_to_create = []
    
    for root, dirs, files in os.walk(content_path):
        rel_root = Path(root).relative_to(content_path)
        
        for filename in files:
            file_path = Path(root) / filename
            rel_path = rel_root / filename
            
            # Skip files in vendored charts directories (charts/*/charts/*)
            # ONLY if we're generating helm pull commands for them
            # When helm_charts is empty, server has already vendored - include these files
            parts = rel_path.parts
            if helm_charts and len(parts) >= 4 and parts[0] == "charts" and parts[2] == "charts":
                # This is a vendored chart file - skip it (will be downloaded via helm pull)
                continue
            
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Binary file - skip for now (shouldn't have many)
                continue
            
            # Check if executable
            is_executable = os.access(file_path, os.X_OK)
            
            files_to_create.append({
                'path': str(rel_path),
                'content': content,
                'executable': is_executable
            })
    
    # Generate mkdir commands for directories
    dirs_to_create = set()
    for f in files_to_create:
        parent = str(Path(f['path']).parent)
        if parent and parent != '.':
            dirs_to_create.add(parent)
    
    mkdir_section = ""
    for d in sorted(dirs_to_create):
        mkdir_section += f'mkdir -p "{d}"\n'
    
    # Generate file creation section using heredocs
    files_section = ""
    for f in files_to_create:
        # Escape content for heredoc (only need to worry about EOF marker)
        content = f['content']
        # Use a unique EOF marker to avoid conflicts
        eof_marker = "FILEEOF"
        while eof_marker in content:
            eof_marker = f"EOF{hash(content) % 10000}"
        
        files_section += f'''
cat << '{eof_marker}' > "{f['path']}"
{content}
{eof_marker}
'''
        if f['executable']:
            files_section += f'chmod +x "{f["path"]}"\n'
    
    # Generate helm repo and pull section from passed chart info
    helm_section = ""
    repos_added = set()
    
    for chart in helm_charts:
        chart_repo = chart.get('repository', '')
        if not chart_repo:
            continue
        
        chart_id = chart.get('id', chart['name'])
        chart_name = chart['name']
        chart_version = chart['version']
        category = chart.get('category', 'apps')
        dest_dir = f"charts/{category}/{chart_id}/charts"
        
        is_oci = chart_repo.startswith("oci://")
        
        if is_oci:
            # OCI registries don't need helm repo add
            # Remove existing chart to avoid "already exists" error from helm pull
            helm_section += f'''rm -rf "{dest_dir}/{chart_name}" 2>/dev/null || true
mkdir -p "{dest_dir}"
helm pull {chart_repo}/{chart_name} --version {chart_version} --untar --untardir "{dest_dir}"
'''
        else:
            # Traditional repos need helm repo add
            # Create unique repo name from URL
            repo_name = chart_repo.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")[:30]
            
            if chart_repo not in repos_added:
                helm_section += f'helm repo add {repo_name} {chart_repo} 2>/dev/null || true\n'
                repos_added.add(chart_repo)
            
            # Remove existing chart to avoid "already exists" error from helm pull
            helm_section += f'''rm -rf "{dest_dir}/{chart_name}" 2>/dev/null || true
mkdir -p "{dest_dir}"
helm pull {repo_name}/{chart_name} --version {chart_version} --untar --untardir "{dest_dir}"
'''
    
    if helm_charts:
        helm_section = f'''
info "Downloading Helm charts from upstream..."
helm repo update 2>/dev/null || true
{helm_section}
success "Helm charts downloaded"
'''
    
    script = f'''#!/usr/bin/env bash
#
# K8s Bootstrap Installer
# Cluster: {cluster_name}
# Repository: {repo_url}
#
# Usage:
#   bash -c "$(curl -fsSL <url>)"
#   bash -c "$(curl -fsSL <url>)" -- -k /path/to/kubeconfig
#

set -euo pipefail

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
NC='\\033[0m'

info() {{ echo -e "${{BLUE}}ℹ${{NC}} $1"; }}
success() {{ echo -e "${{GREEN}}✓${{NC}} $1"; }}
warn() {{ echo -e "${{YELLOW}}⚠${{NC}} $1"; }}
error() {{ echo -e "${{RED}}✗${{NC}} $1" >&2; }}

# ============================================================================
# Configuration
# ============================================================================
CLUSTER_NAME="{cluster_name}"
REPO_URL="{repo_url}"
BRANCH="{branch}"

# ============================================================================
# Arguments
# ============================================================================
KUBECONFIG_ARG=""
CONTEXT_ARG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--kubeconfig) KUBECONFIG_ARG="$2"; shift 2 ;;
        -c|--context) CONTEXT_ARG="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -k, --kubeconfig PATH   Custom kubeconfig"
            echo "  -c, --context NAME      Kubernetes context"
            echo "  -h, --help              Show help"
            echo ""
            echo "For updates, use the Update mode in the UI"
            exit 0
            ;;
        --) shift; break ;;
        *) break ;;
    esac
done

# Helper for kubectl/helm with custom kubeconfig
kctl() {{
    local args=()
    [[ -n "$KUBECONFIG_ARG" ]] && args+=(--kubeconfig "$KUBECONFIG_ARG")
    [[ -n "$CONTEXT_ARG" ]] && args+=(--context "$CONTEXT_ARG")
    kubectl "${{args[@]}}" "$@"
}}

hlm() {{
    local args=()
    [[ -n "$KUBECONFIG_ARG" ]] && args+=(--kubeconfig "$KUBECONFIG_ARG")
    [[ -n "$CONTEXT_ARG" ]] && args+=(--kube-context "$CONTEXT_ARG")
    helm "${{args[@]}}" "$@"
}}

# ============================================================================
# Main
# ============================================================================
echo ""
echo -e "${{CYAN}}╔══════════════════════════════════════════════════════════════╗${{NC}}"
echo -e "${{CYAN}}║       K8s Bootstrap - {cluster_name:<36} ║${{NC}}"
echo -e "${{CYAN}}╚══════════════════════════════════════════════════════════════╝${{NC}}"
echo ""

# Check tools
for cmd in kubectl helm git; do
    command -v $cmd &>/dev/null || {{ error "$cmd not installed"; exit 1; }}
done
success "Required tools installed"

# Check cluster
if ! kctl cluster-info &>/dev/null; then
    error "Cannot connect to Kubernetes cluster"
    exit 1
fi
success "Connected to cluster"

# Setup directory
TARGET_DIR="./$CLUSTER_NAME"

if [[ -d "$TARGET_DIR" ]]; then
    error "Directory already exists: $TARGET_DIR"
    error "For updates, use the Update mode in the UI or run the update script"
    exit 1
fi

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"
info "Working in: $(pwd)"

# ============================================================================
# Create directory structure
# ============================================================================
info "Creating directories..."
{mkdir_section}

# ============================================================================
# Create files
# ============================================================================
info "Creating files..."
{files_section}
success "Files created"

# ============================================================================
# Download Helm charts
# ============================================================================
{helm_section}

# ============================================================================
# Run bootstrap
# ============================================================================
chmod +x bootstrap.sh

info "Starting bootstrap..."
BOOTSTRAP_ARGS=()
[[ -n "$KUBECONFIG_ARG" ]] && BOOTSTRAP_ARGS+=(-k "$KUBECONFIG_ARG")
[[ -n "$CONTEXT_ARG" ]] && BOOTSTRAP_ARGS+=(-c "$CONTEXT_ARG")

exec ./bootstrap.sh "${{BOOTSTRAP_ARGS[@]}}"
'''
    
    return script


@app.get("/api/preview")

async def preview_structure(
    cluster_name: str = "my-cluster",
    components: str = "cert-manager,ingress-nginx"
):
    """Preview generated structure without downloading"""
    component_ids = [c.strip() for c in components.split(",") if c.strip()]
    definitions = definition_loader.load_all()
    
    # Validate instance/operator dependencies
    enabled_ids = set(component_ids)
    validation_errors = validate_instance_operators(enabled_ids, definitions)
    if validation_errors:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid selection: {'; '.join(validation_errors)}"
        )
    
    # Resolve dependencies
    all_component_ids = resolve_dependencies(enabled_ids, definitions)
    
    # Build component list (namespaces managed via namespaces chart)
    selected = []
    
    for comp_id in all_component_ids:
        comp_def = definitions.get(comp_id)
        if not comp_def or comp_id == "namespaces":
            continue
        
        selected.append({
            "definition": comp_def,
            "values": comp_def.get("defaultValues", {}),
            "raw_overrides": ""
        })
    
    # Generate preview structure
    temp_dir = tempfile.mkdtemp(prefix="k8s-bootstrap-preview-")
    try:
        generator = RepoGenerator(
            output_dir=temp_dir,
            cluster_name=cluster_name,
            repo_url="git@github.com:example/repo.git",
            branch="main"
        )
        
        repo_path = generator.generate(selected)
        
        # Build tree structure
        tree = build_tree(repo_path)
        return {"tree": tree}
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/resolve-dependencies")
async def resolve_deps(components: str):
    """
    Preview which components will be auto-included.
    Also validates instance/operator dependencies.
    Useful for showing users what dependencies/CRDs will be added.
    """
    component_ids = [c.strip() for c in components.split(",") if c.strip()]
    definitions = definition_loader.load_all()
    
    enabled_ids = set(component_ids)
    
    # Validate instance/operator dependencies
    validation_errors = validate_instance_operators(enabled_ids, definitions)
    
    all_ids = resolve_dependencies(enabled_ids, definitions)
    
    # Categorize results
    result = {
        "requested": list(enabled_ids),
        "auto_included": [],
        "crds": [],
        "always_included": [],
        "total": [],
        "valid": len(validation_errors) == 0,
        "validation_errors": validation_errors
    }
    
    for comp_id in all_ids:
        comp_def = definitions.get(comp_id, {})
        
        # Skip namespaces - managed via namespaces chart
        if comp_id == "namespaces":
            continue
        
        if comp_id in enabled_ids:
            continue  # Already in requested
        elif comp_def.get("alwaysInclude"):
            result["always_included"].append(comp_id)
        elif comp_id.endswith("-crds"):
            result["crds"].append(comp_id)
        else:
            result["auto_included"].append(comp_id)
    
    # Filter namespaces from total list as well
    result["total"] = [c for c in all_ids if c != "namespaces"]
    
    return result


def build_tree(path: str, prefix: str = "") -> List[Dict]:
    """Build directory tree structure"""
    result = []
    entries = sorted(os.listdir(path))
    
    for entry in entries:
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path):
            result.append({
                "name": entry,
                "type": "directory",
                "children": build_tree(entry_path)
            })
        else:
            result.append({
                "name": entry,
                "type": "file"
            })
    
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
