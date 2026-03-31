"""
Main API router that combines all route modules
"""
from fastapi import APIRouter

from app.api.routes import bundles, categories, components, bootstrap, docs

api_router = APIRouter()

# Include all route modules
api_router.include_router(bundles.router, prefix="/bundles", tags=["bundles"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(components.router, prefix="/components", tags=["components"])
api_router.include_router(bootstrap.router, tags=["bootstrap"])
api_router.include_router(docs.router, prefix="/docs", tags=["docs"])
