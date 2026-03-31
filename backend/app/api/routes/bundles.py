"""
Bundle API routes
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import get_bundle_service
from app.core.utils import is_valid_identifier

router = APIRouter()


@router.get("")
async def list_bundles(show_hidden: bool = False):
    """List available bundles.

    Returns all visible bundles by default. Pass ``show_hidden=true``
    to include development/experimental bundles (e.g. multi-tenant-stack).
    """
    service = get_bundle_service()
    return service.list_bundles(show_hidden=show_hidden)


@router.get("/{bundle_id}")
async def get_bundle(bundle_id: str):
    """Get a specific bundle by ID, including its full component list, parameters, and notes."""
    service = get_bundle_service()
    
    if not is_valid_identifier(bundle_id):
        raise HTTPException(status_code=400, detail="Invalid bundle ID")
    
    bundle = service.get_bundle(bundle_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Bundle not found")
    
    return bundle
