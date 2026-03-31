"""
K8s Bootstrap - FastAPI Backend
Generates GitOps bootstrap repositories for Kubernetes clusters

This is the main application entry point. The actual implementation is split across:
- app/models/     - Pydantic models for API requests/responses
- app/services/   - Business logic layer
- app/api/routes/ - API endpoint handlers
- app/generator/  - Repository and script generation
- app/core/       - Configuration and utilities
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.router import api_router
from app.api.routes.scripts import router as scripts_router

# Create FastAPI application
app = FastAPI(
    title="K8s Bootstrap",
    description="Generate GitOps bootstrap repositories for Kubernetes",
    version="1.0.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

# API routes (POST /api/bootstrap, /api/update, etc.)
app.include_router(api_router, prefix="/api")

# Script delivery routes at root level for clean curl commands
# GET /bootstrap/{token}, GET /update/{token}
app.include_router(scripts_router, tags=["scripts"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
