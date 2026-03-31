"""
Shared dependencies for API routes
"""
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.definitions import DefinitionLoader
from app.services.bundle_service import BundleService
from app.services.bootstrap_service import BootstrapService


@lru_cache()
def get_definition_loader() -> DefinitionLoader:
    """Get cached definition loader instance"""
    return DefinitionLoader(settings.definitions_path)


@lru_cache()
def get_bundle_service() -> BundleService:
    """Get cached bundle service instance"""
    bundles_path = Path(settings.definitions_path).parent / "bundles"
    return BundleService(bundles_path)


def get_bootstrap_service() -> BootstrapService:
    """Get bootstrap service instance (new instance each time for thread safety)"""
    return BootstrapService(get_definition_loader())


# Paths
DOCS_PATH = Path("/app/docs") if Path("/app/docs").exists() else Path(__file__).parent.parent.parent / "docs"
