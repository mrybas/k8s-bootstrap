"""
Pydantic models for components, categories, and bundles
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class ComponentInfo(BaseModel):
    """Component information for API responses"""
    id: str
    name: str
    description: str
    icon: str = ""
    version: str = ""
    hasConfig: bool = False
    docsUrl: str = ""
    # Operator pattern
    isOperator: bool = False
    operatorFor: str = ""
    suggestsInstances: List[str] = []
    suggestsComponents: List[str] = []
    # Instance pattern
    isInstance: bool = False
    instanceOf: str = ""
    # Multi-instance pattern
    multiInstance: bool = False
    defaultNamespace: str = ""
    requiresOperator: str = ""


class CategoryInfo(BaseModel):
    """Category information for API responses"""
    id: str
    name: str
    description: str = ""
    icon: str = "📦"
    priority: int = 100
    components: List[ComponentInfo] = []


class BundleComponent(BaseModel):
    """Component reference in a bundle"""
    id: str
    required: bool = True
    recommended: bool = False
    description: str = ""
    values: Optional[Dict[str, Any]] = None


class BundleParameter(BaseModel):
    """Configurable parameter in a bundle"""
    id: str
    name: str
    description: str
    type: str  # string, boolean, select
    default: Any
    required: bool = False
    options: Optional[List[str]] = None
    applies_to: str  # Component ID or '_bootstrap' or '_domain'
    path: str  # Path in component values or special key


class BundleNote(BaseModel):
    """Information note in a bundle"""
    title: str
    content: str


class BundleCniBootstrap(BaseModel):
    """CNI bootstrap configuration"""
    enabled: bool = False
    component: str = ""
    description: str = ""


class BundleDnsBootstrap(BaseModel):
    """DNS bootstrap configuration"""
    enabled: bool = False
    component: str = ""
    description: str = ""


class Bundle(BaseModel):
    """Bundle definition"""
    id: str
    name: str
    description: str
    icon: str = "📦"
    category: str = "general"
    components: List[BundleComponent] = []
    parameters: List[BundleParameter] = []
    notes: List[BundleNote] = []
    cni_bootstrap: Optional[BundleCniBootstrap] = None
    dns_bootstrap: Optional[BundleDnsBootstrap] = None
    install_order: List[str] = []
