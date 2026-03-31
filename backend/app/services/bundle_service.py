"""
Bundle business logic service
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

from app.core.utils import is_valid_identifier

logger = logging.getLogger("k8s_bootstrap.services.bundle")


class BundleService:
    """Service for bundle-related business logic"""
    
    def __init__(self, bundles_path: Path):
        self.bundles_path = bundles_path
    
    def list_bundles(self, show_hidden: bool = False) -> List[Dict[str, Any]]:
        """Get all available bundles"""
        if not self.bundles_path.exists():
            return []

        bundles = []
        for f in sorted(self.bundles_path.glob("*.yaml")):
            try:
                with open(f, 'r') as file:
                    bundle = yaml.safe_load(file)
                    if bundle and 'id' in bundle:
                        if not show_hidden and bundle.get("hidden", False):
                            continue
                        bundles.append({
                            "id": bundle["id"],
                            "name": bundle["name"],
                            "description": bundle.get("description", ""),
                            "icon": bundle.get("icon", "📦"),
                            "category": bundle.get("category", "general"),
                            "hidden": bundle.get("hidden", False),
                            "components": bundle.get("components", []),
                            "parameters": bundle.get("parameters", []),
                            "notes": bundle.get("notes", []),
                            "cni_bootstrap": bundle.get("cni_bootstrap"),
                        })
            except Exception as e:
                logger.warning(f"Error loading bundle {f}: {e}")

        return bundles
    
    def get_bundle(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific bundle by ID"""
        if not is_valid_identifier(bundle_id):
            return None
        
        bundle_path = self.bundles_path / f"{bundle_id}.yaml"
        if not bundle_path.exists():
            return None
        
        try:
            with open(bundle_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Error loading bundle {bundle_id}: {e}")
            return None
