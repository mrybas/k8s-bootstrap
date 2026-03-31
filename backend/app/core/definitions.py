"""
Component and category definition loader
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml

logger = logging.getLogger("k8s_bootstrap.definitions")


class DefinitionLoader:
    """Loads component definitions from YAML files"""
    
    def __init__(self, definitions_path: Path):
        self.definitions_path = definitions_path
        self._cache: Optional[Dict[str, Any]] = None
        self._categories_cache: Optional[Dict[str, Any]] = None
    
    def load_categories(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load categories from categories.yaml"""
        if self._categories_cache is not None and not force_reload:
            return self._categories_cache
        
        categories_file = self.definitions_path.parent / "categories.yaml"
        
        if categories_file.exists():
            try:
                with open(categories_file, 'r') as f:
                    data = yaml.safe_load(f)
                    self._categories_cache = data.get("categories", {})
            except Exception as e:
                logger.warning(f"Error loading categories: {e}")
                self._categories_cache = {}
        else:
            # Default categories
            self._categories_cache = {
                "apps": {"name": "Apps", "icon": "📦", "description": "Applications", "priority": 100}
            }
        
        return self._categories_cache
    
    def load_all(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load all component definitions"""
        if self._cache is not None and not force_reload:
            return self._cache
        
        definitions = {}
        
        if not self.definitions_path.exists():
            return definitions
        
        for file_path in self.definitions_path.glob("*.yaml"):
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                    if data and 'id' in data:
                        definitions[data['id']] = data
            except Exception as e:
                logger.warning(f"Error loading {file_path}: {e}")
        
        # Sort by priority/order
        self._cache = dict(sorted(
            definitions.items(),
            key=lambda x: x[1].get('priority', 100)
        ))
        
        return self._cache
    
    def get(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Get single component definition"""
        definitions = self.load_all()
        return definitions.get(component_id)
    
    def reload(self):
        """Force reload definitions and categories"""
        self._cache = None
        self._categories_cache = None
        return self.load_all()


# Global loader instance
_loader: Optional[DefinitionLoader] = None


def get_loader() -> DefinitionLoader:
    """Get or create the global definition loader"""
    global _loader
    if _loader is None:
        from app.core.config import settings
        # settings.definitions_path already points to 'definitions/components'
        _loader = DefinitionLoader(Path(settings.definitions_path))
    return _loader


def get_categories() -> Dict[str, Any]:
    """Get all categories from the global loader"""
    return get_loader().load_categories()


def reload_global_loader():
    """Force reload the global loader's caches (definitions + categories)."""
    loader = get_loader()
    loader.reload()
    loader.load_categories(force_reload=True)
    return loader


def load_tenant_addons() -> List[Dict[str, Any]]:
    """Load tenant addon definitions from components with tenantAddon: true."""
    loader = get_loader()
    all_components = loader.load_all()

    addons = []
    for comp_id, defn in all_components.items():
        if not defn.get("tenantAddon"):
            continue
        addons.append(defn)

    # Sort by tenantConfig.order
    addons.sort(key=lambda x: x.get("tenantConfig", {}).get("order", 100))
    return addons
