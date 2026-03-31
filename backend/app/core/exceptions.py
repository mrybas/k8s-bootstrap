"""
Custom exceptions for K8s Bootstrap
"""


class K8sBootstrapError(Exception):
    """Base exception for all K8s Bootstrap errors"""
    pass


class ValidationError(K8sBootstrapError):
    """Raised when validation fails"""
    pass


class ComponentNotFoundError(K8sBootstrapError):
    """Raised when a component is not found"""
    pass


class BundleNotFoundError(K8sBootstrapError):
    """Raised when a bundle is not found"""
    pass


class SessionNotFoundError(K8sBootstrapError):
    """Raised when a session token is invalid or expired"""
    pass


class ChartGenerationError(K8sBootstrapError):
    """Raised when chart generation fails"""
    pass


class DefinitionLoadError(K8sBootstrapError):
    """Raised when definition loading fails"""
    pass
