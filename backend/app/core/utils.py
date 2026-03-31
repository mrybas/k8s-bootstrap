"""
Shared utility functions
"""
from typing import Dict, Any
import yaml


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.
    
    Values from 'override' take precedence over 'base'.
    Nested dicts are merged recursively.
    
    Args:
        base: Base dictionary
        override: Dictionary with override values
        
    Returns:
        New merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def parse_yaml_safe(content: str) -> Dict[str, Any]:
    """
    Safely parse YAML content.
    
    Args:
        content: YAML string
        
    Returns:
        Parsed dict (empty dict if content is empty or None)
        
    Raises:
        yaml.YAMLError: If YAML is invalid
    """
    if not content or not content.strip():
        return {}
    
    result = yaml.safe_load(content)
    return result if isinstance(result, dict) else {}


def is_valid_identifier(value: str) -> bool:
    """
    Check if value is a valid identifier (alphanumeric with - and _).
    
    Used for validating cluster names, bundle IDs, doc IDs, etc.
    """
    if not value:
        return False
    return value.replace("-", "").replace("_", "").isalnum()


def sanitize_cluster_name(name: str) -> str:
    """
    Sanitize cluster name for use in file paths and Kubernetes resources.
    
    - Lowercase
    - Replace spaces and underscores with hyphens
    - Remove invalid characters
    """
    return name.lower().replace("_", "-").replace(" ", "-")
