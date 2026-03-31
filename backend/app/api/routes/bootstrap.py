"""
Bootstrap and Update API routes

POST endpoints for creating sessions (called by UI).
GET endpoints for script delivery are in scripts.py (mounted at root).
"""
import tempfile
import shutil

from fastapi import APIRouter, HTTPException

from app.api.deps import get_definition_loader, get_bootstrap_service
from app.core.definitions import reload_global_loader
from app.models.api import (
    GenerateRequest,
    BootstrapCreateResponse,
    UpdateCreateResponse,
)
from app.services.component_service import ComponentService
from app.generator.repo_generator import RepoGenerator

router = APIRouter()


@router.post("/bootstrap", response_model=BootstrapCreateResponse)
async def create_bootstrap(request: GenerateRequest):
    """Create a bootstrap session and return a one-time curl command."""
    service = get_bootstrap_service()
    
    try:
        result = service.create_bootstrap(request)
        return BootstrapCreateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update", response_model=UpdateCreateResponse)
async def create_update(request: GenerateRequest):
    """Create an update session for existing installations."""
    service = get_bootstrap_service()
    
    try:
        result = service.create_update(request)
        return UpdateCreateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preview")
async def preview_structure(
    cluster_name: str = "my-cluster",
    components: str = "cert-manager,ingress-nginx"
):
    """Preview generated structure without downloading"""
    import os
    
    component_ids = [c.strip() for c in components.split(",") if c.strip()]
    
    loader = get_definition_loader()
    definitions = loader.load_all()
    
    enabled_ids = set(component_ids)
    
    # Validate
    validation_errors = ComponentService.validate_instance_operators(enabled_ids, definitions)
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid selection: {'; '.join(validation_errors)}"
        )
    
    # Resolve
    all_component_ids = ComponentService.resolve_dependencies(enabled_ids, definitions)
    
    # Build component list
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
    
    # Generate preview
    temp_dir = tempfile.mkdtemp(prefix="k8s-bootstrap-preview-")
    try:
        generator = RepoGenerator(
            output_dir=temp_dir,
            cluster_name=cluster_name,
            repo_url="git@github.com:example/repo.git",
            branch="main"
        )
        
        repo_path = generator.generate(selected)
        tree = _build_tree(repo_path)
        return {"tree": tree}
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/reload-definitions")
async def reload_definitions():
    """Force reload component and bundle definitions from disk.
    
    Reloads both the API loader (deps.py) and the global loader
    used by repo_generator for categories.
    """
    # Reload the deps.py loader (used by API routes)
    loader = get_definition_loader()
    definitions = loader.reload()
    loader.load_categories(force_reload=True)
    
    # Reload the global loader (used by repo_generator for categories)
    reload_global_loader()
    
    return {
        "status": "ok",
        "components_loaded": len(definitions),
        "component_ids": sorted(definitions.keys())
    }


def _build_tree(path: str):
    """Build directory tree structure"""
    import os
    
    result = []
    entries = sorted(os.listdir(path))
    
    for entry in entries:
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path):
            result.append({
                "name": entry,
                "type": "directory",
                "children": _build_tree(entry_path)
            })
        else:
            result.append({
                "name": entry,
                "type": "file"
            })
    
    return result
