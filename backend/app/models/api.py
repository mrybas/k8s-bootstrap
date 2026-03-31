"""
Pydantic models for API requests and responses
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class ComponentInstance(BaseModel):
    """Instance configuration for multi-instance components"""
    name: str
    namespace: str
    values: Dict[str, Any] = {}
    raw_overrides: str = ""


class ComponentSelection(BaseModel):
    """Component selection with values"""
    id: str
    enabled: bool = True
    values: Dict[str, Any] = {}
    raw_overrides: str = ""
    instances: Optional[List[ComponentInstance]] = None


class GitAuthConfig(BaseModel):
    """Git authentication configuration for private repositories"""
    enabled: bool = False
    platform: str = "github"  # github, gitlab, gitea
    customUrl: Optional[str] = None  # For self-hosted GitLab/Gitea
    username: Optional[str] = None
    password: Optional[str] = None


class GenerateRequest(BaseModel):
    """Request to generate bootstrap package"""
    cluster_name: str
    repo_url: str
    branch: str = "main"
    components: List[ComponentSelection]
    git_auth: Optional[GitAuthConfig] = None
    skip_git_push: bool = False
    cni_bootstrap: Optional[str] = None
    dns_bootstrap: Optional[str] = None
    bundle_config: Optional[Dict[str, Any]] = None


class BootstrapCreateResponse(BaseModel):
    """Response from bootstrap creation"""
    token: str
    curl_command: str
    expires_in_minutes: int
    one_time: bool


class UpdateCreateResponse(BaseModel):
    """Response from update creation"""
    token: str
    curl_command: str
    expires_in_minutes: int
    one_time: bool
    files_count: int
    charts_count: int
