"""
Application configuration
"""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # API settings
    api_title: str = "K8s Bootstrap API"
    api_version: str = "1.0.0"
    debug: bool = False
    
    # CORS - frontend URLs
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"]
    
    # Paths
    definitions_path: Path = Path(__file__).parent.parent.parent / "definitions" / "components"
    
    # Session TTL in minutes
    session_ttl_minutes: int = 60
    
    class Config:
        env_prefix = "K8S_BOOTSTRAP_"


settings = Settings()
