"""
Update Generator
Generates update script for existing k8s-bootstrap installations.

Unlike the bootstrap script which creates everything from scratch,
the update script:
- Only syncs changed files (preserves unchanged)
- Skips charts with unchanged versions
- Preserves git history
- Triggers Flux reconciliation for changed components
"""
import os
from pathlib import Path
from typing import List, Dict, Any

from .template_engine import render


class UpdateGenerator:
    """Generates update script for existing installations"""
    
    def __init__(
        self,
        cluster_name: str,
        repo_url: str,
        branch: str = "main",
        git_auth_enabled: bool = False,
        git_platform: str = "github"
    ):
        self.cluster_name = cluster_name
        self.repo_url = repo_url
        self.branch = branch
        self.git_auth_enabled = git_auth_enabled
        self.git_platform = git_platform
    
    def generate_update_script(
        self,
        new_files: List[Dict[str, Any]],
        helm_charts: List[Dict[str, str]]
    ) -> str:
        """
        Generate update.sh script.
        
        Args:
            new_files: List of files with path, content, and checksum
            helm_charts: List of charts with id, name, version, repository
            
        Returns:
            Update script content
        """
        # Build file manifest for the script
        file_manifest = []
        for f in new_files:
            file_manifest.append({
                "path": f["path"],
                "checksum": f.get("checksum", ""),
                "executable": f.get("executable", False)
            })
        
        context = {
            "cluster_name": self.cluster_name,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "git_auth_enabled": self.git_auth_enabled,
            "git_platform": self.git_platform,
            "file_manifest": file_manifest,
            "helm_charts": helm_charts,
            "new_files": new_files,
        }
        
        return render("scripts/update.sh.j2", **context)


def calculate_file_checksum(content: str) -> str:
    """Calculate MD5 checksum of content"""
    import hashlib
    return hashlib.md5(content.encode('utf-8')).hexdigest()
