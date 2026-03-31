"""
Component business logic service
"""
import logging
from typing import Dict, List, Set, Any, Tuple
from app.models.api import ComponentSelection
from app.core.utils import is_valid_identifier
from app.generator.chart_generator import ChartGenerator

logger = logging.getLogger(__name__)


class ComponentService:
    """Service for component-related business logic"""
    
    @staticmethod
    def validate_cluster_name(cluster_name: str) -> bool:
        """Validate cluster name format"""
        return is_valid_identifier(cluster_name)
    
    @staticmethod
    def validate_instance_operators(
        selected_ids: Set[str],
        definitions: Dict[str, Any]
    ) -> List[str]:
        """
        Validate that all instance components have their operators selected.
        Returns list of validation error messages (empty if valid).
        """
        errors = []
        for comp_id in selected_ids:
            comp_def = definitions.get(comp_id, {})
            if comp_def.get("isInstance") and comp_def.get("instanceOf"):
                operator_id = comp_def["instanceOf"]
                if operator_id not in selected_ids:
                    errors.append(
                        f"'{comp_def.get('name', comp_id)}' requires '{operator_id}' to be selected"
                    )
        return errors
    
    @staticmethod
    def resolve_dependencies(
        selected_ids: Set[str],
        definitions: Dict[str, Any]
    ) -> List[str]:
        """
        Resolve component dependencies and auto-includes.
        Returns ordered list of component IDs to install.
        """
        all_components: Set[str] = set(selected_ids)
        
        # Add always-included components (like flux)
        for comp_id, comp_def in definitions.items():
            if comp_def.get("alwaysInclude", False):
                all_components.add(comp_id)
        
        # Iteratively resolve dependencies
        changed = True
        while changed:
            changed = False
            for comp_id in list(all_components):
                comp_def = definitions.get(comp_id, {})
                
                # Add required CRDs
                if "requiresCrds" in comp_def:
                    crds = comp_def["requiresCrds"]
                    if isinstance(crds, str):
                        crds = [crds]
                    for crd in crds:
                        if crd not in all_components and crd in definitions:
                            all_components.add(crd)
                            changed = True
                
                # Add dependencies
                for dep in comp_def.get("dependsOn", []):
                    if dep not in all_components and dep in definitions:
                        all_components.add(dep)
                        changed = True
        
        # Check for auto-include components based on what's selected
        for comp_id, comp_def in definitions.items():
            if comp_id in all_components:
                continue
            
            auto_include = comp_def.get("autoInclude", {})
            when_components = auto_include.get("when", [])
            if when_components:
                if any(w in all_components for w in when_components):
                    all_components.add(comp_id)
        
        # Sort by priority
        sorted_components = sorted(
            all_components,
            key=lambda cid: definitions.get(cid, {}).get("priority", 100)
        )
        
        return sorted_components
    
    @staticmethod
    def validate_raw_yaml(components: List[ComponentSelection]) -> List[str]:
        """Validate raw YAML overrides for all components"""
        errors = []
        for comp in components:
            if comp.enabled and comp.raw_overrides:
                is_valid, error_msg = ChartGenerator.validate_raw_yaml(
                    comp.raw_overrides, comp.id
                )
                if not is_valid:
                    errors.append(error_msg)
        return errors
    
    @staticmethod
    def build_selection_map(
        components: List[ComponentSelection]
    ) -> Tuple[Dict[str, ComponentSelection], Set[str]]:
        """Build selection map and enabled IDs set from request"""
        user_selections: Dict[str, ComponentSelection] = {}
        enabled_ids: Set[str] = set()
        
        for comp in components:
            if comp.enabled:
                user_selections[comp.id] = comp
                enabled_ids.add(comp.id)
        
        return user_selections, enabled_ids
    
    @staticmethod
    def build_component_list(
        component_ids: List[str],
        definitions: Dict[str, Any],
        user_selections: Dict[str, ComponentSelection]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """
        Build the component list and helm charts info from resolved IDs.
        
        Returns:
            (selected_components, helm_charts_info)
        """
        selected = []
        helm_charts_info = []
        
        for comp_id in component_ids:
            comp_def = definitions.get(comp_id)
            if not comp_def:
                if comp_id != "namespaces":
                    logger.warning(f"Component '{comp_id}' not found in definitions — skipped. Restart backend to reload definitions.")
                continue
            if comp_id == "namespaces":
                continue
            
            user_sel = user_selections.get(comp_id)
            
            # Handle multi-instance components
            if comp_def.get("multiInstance") and user_sel and user_sel.instances:
                for instance in user_sel.instances:
                    instance_def = dict(comp_def)
                    instance_def["_instance_name"] = instance.name
                    instance_def["namespace"] = instance.namespace
                    
                    selected.append({
                        "definition": instance_def,
                        "values": instance.values,
                        "raw_overrides": instance.raw_overrides
                    })
            else:
                # Single instance (default behavior)
                values = user_sel.values if user_sel else comp_def.get("defaultValues", {})
                raw_overrides = user_sel.raw_overrides if user_sel else ""
                
                selected.append({
                    "definition": comp_def,
                    "values": values,
                    "raw_overrides": raw_overrides
                })
            
            # Collect chart info for helm pull commands
            if comp_def.get("chartType") not in ("custom", "meta") and comp_def.get("upstream"):
                upstream = comp_def["upstream"]
                helm_charts_info.append({
                    "id": comp_def["id"],
                    "category": comp_def.get("category", "apps"),
                    "name": upstream.get("chartName", comp_def["id"]),
                    "version": upstream.get("version", "*"),
                    "repository": upstream.get("repository", "")
                })
        
        return selected, helm_charts_info
