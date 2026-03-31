"""
Categories API routes
"""
from fastapi import APIRouter

from app.api.deps import get_definition_loader

router = APIRouter()


@router.get("")
async def get_categories():
    """Get all component categories (excluding hidden components)"""
    loader = get_definition_loader()
    definitions = loader.load_all()
    category_defs = loader.load_categories()
    
    categories = {}
    
    for comp in definitions.values():
        # Skip hidden components
        if comp.get("hidden", False):
            continue
        
        cat = comp.get("category", "other")
        if cat not in categories:
            cat_def = category_defs.get(cat, {})
            categories[cat] = {
                "id": cat,
                "name": cat_def.get("name", comp.get("categoryName", cat.title())),
                "description": cat_def.get("description", comp.get("categoryDescription", "")),
                "icon": cat_def.get("icon", "📦"),
                "priority": cat_def.get("priority", 100),
                "components": []
            }
        
        # Build component info
        comp_info = {
            "id": comp["id"],
            "name": comp["name"],
            "description": comp["description"],
            "icon": comp.get("icon", ""),
            "version": comp.get("upstream", {}).get("version", ""),
            "hasConfig": bool(comp.get("jsonSchema")),
            "docsUrl": comp.get("docsUrl", ""),
            # Operator pattern
            "isOperator": comp.get("isOperator", False),
            "operatorFor": comp.get("operatorFor", ""),
            "suggestsInstances": comp.get("suggestsInstances", []),
            "suggestsComponents": comp.get("suggestsComponents", []),
            # Instance pattern
            "isInstance": comp.get("isInstance", False),
            "instanceOf": comp.get("instanceOf", ""),
            # Multi-instance pattern
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
    
    # Sort categories by priority
    result = [cat for cat in categories.values() if cat["components"]]
    result.sort(key=lambda c: c.get("priority", 100))
    
    return result
