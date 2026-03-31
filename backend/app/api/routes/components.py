"""
Components API routes
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import get_definition_loader
from app.services.component_service import ComponentService

router = APIRouter()


@router.get("")
async def get_components():
    """Get all available components (excluding hidden)"""
    loader = get_definition_loader()
    definitions = loader.load_all()
    
    result = []
    for comp in definitions.values():
        if comp.get("hidden", False):
            continue
        
        comp_info = dict(comp)
        comp_info["hasConfig"] = bool(comp.get("jsonSchema"))
        result.append(comp_info)
    
    return result


@router.get("/{component_id}")
async def get_component(component_id: str):
    """Get component definition with UI schema"""
    loader = get_definition_loader()
    definitions = loader.load_all()
    
    if component_id not in definitions:
        raise HTTPException(status_code=404, detail="Component not found")
    
    comp = definitions[component_id]
    return {
        **comp,
        "hasConfig": bool(comp.get("jsonSchema")),
    }


@router.get("/{component_id}/schema")
async def get_component_schema(component_id: str):
    """Get UI schema for component configuration form"""
    loader = get_definition_loader()
    definitions = loader.load_all()
    
    if component_id not in definitions:
        raise HTTPException(status_code=404, detail="Component not found")
    
    comp = definitions[component_id]
    return {
        "jsonSchema": comp.get("jsonSchema", {}),
        "uiSchema": comp.get("uiSchema", {}),
        "defaultValues": comp.get("defaultValues", {})
    }


@router.get("/resolve-dependencies")
async def resolve_dependencies(components: str):
    """
    Preview which components will be auto-included.
    Also validates instance/operator dependencies.
    """
    component_ids = [c.strip() for c in components.split(",") if c.strip()]
    
    loader = get_definition_loader()
    definitions = loader.load_all()
    
    enabled_ids = set(component_ids)
    
    # Validate
    validation_errors = ComponentService.validate_instance_operators(enabled_ids, definitions)
    
    # Resolve
    all_ids = ComponentService.resolve_dependencies(enabled_ids, definitions)
    
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
        
        if comp_id == "namespaces":
            continue
        
        if comp_id in enabled_ids:
            continue
        elif comp_def.get("alwaysInclude"):
            result["always_included"].append(comp_id)
        elif comp_id.endswith("-crds"):
            result["crds"].append(comp_id)
        else:
            result["auto_included"].append(comp_id)
    
    result["total"] = [c for c in all_ids if c != "namespaces"]
    
    return result
