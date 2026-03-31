"""
Script delivery endpoints (for curl commands)

These endpoints are mounted at root level (not /api) for cleaner curl commands:
  curl -sSL http://host/bootstrap/{token} | bash
"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.api.deps import get_bootstrap_service

router = APIRouter()


@router.get("/bootstrap/{token}")
async def get_bootstrap_script(token: str):
    """Return a self-contained bootstrap script. Token is one-time use."""
    service = get_bootstrap_service()
    script = service.get_bootstrap_script(token)
    
    if not script:
        return PlainTextResponse(
            content='#!/bin/bash\necho "Error: Invalid or expired bootstrap token"\nexit 1',
            media_type="text/plain",
            status_code=404
        )
    
    return PlainTextResponse(content=script, media_type="text/plain")


@router.get("/update/{token}")
async def get_update_script(token: str):
    """Return the update script. Token is one-time use."""
    service = get_bootstrap_service()
    script = service.get_update_script(token)
    
    if not script:
        return PlainTextResponse(
            content='#!/bin/bash\necho "Error: Invalid or expired update token"\nexit 1',
            media_type="text/plain",
            status_code=404
        )
    
    return PlainTextResponse(content=script, media_type="text/plain")
