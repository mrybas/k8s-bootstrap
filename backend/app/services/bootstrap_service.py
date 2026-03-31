"""
Bootstrap generation service
"""
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.storage import get_storage
from app.models.api import GenerateRequest, GitAuthConfig
from app.services.component_service import ComponentService
from app.generator.repo_generator import RepoGenerator
from app.generator.bootstrap_generator import GitAuthConfig as BootstrapGitAuthConfig
from app.generator.update_generator import UpdateGenerator, calculate_file_checksum


class BootstrapService:
    """Service for generating bootstrap and update packages"""
    
    def __init__(self, definition_loader):
        self.definition_loader = definition_loader
        self.component_service = ComponentService()
    
    def process_request(
        self,
        request: GenerateRequest,
        validate_yaml: bool = True
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]:
        """
        Process component selection from request.
        
        Returns:
            (selected_components, helm_charts_info, user_selections)
        """
        definitions = self.definition_loader.load_all()
        
        # Validate cluster name
        if not ComponentService.validate_cluster_name(request.cluster_name):
            raise ValueError("Invalid cluster name")
        
        # Build selection map
        user_selections, enabled_ids = ComponentService.build_selection_map(
            request.components
        )
        
        if not enabled_ids:
            raise ValueError("No components selected")
        
        # Validate instance/operator dependencies
        validation_errors = ComponentService.validate_instance_operators(
            enabled_ids, definitions
        )
        if validation_errors:
            raise ValueError(f"Invalid selection: {'; '.join(validation_errors)}")
        
        # Validate raw YAML overrides
        if validate_yaml:
            yaml_errors = ComponentService.validate_raw_yaml(request.components)
            if yaml_errors:
                raise ValueError(f"Invalid raw YAML: {'; '.join(yaml_errors)}")
        
        # Resolve dependencies
        all_component_ids = ComponentService.resolve_dependencies(
            enabled_ids, definitions
        )
        
        # Build component list
        selected, helm_charts_info = ComponentService.build_component_list(
            all_component_ids, definitions, user_selections
        )
        
        return selected, helm_charts_info, user_selections
    
    def create_bootstrap(
        self,
        request: GenerateRequest
    ) -> Dict[str, Any]:
        """
        Create a bootstrap session.
        
        Returns dict with: token, curl_command, expires_in_minutes, one_time
        """
        selected, helm_charts_info, _ = self.process_request(
            request, validate_yaml=True
        )
        
        temp_dir = tempfile.mkdtemp(prefix="k8s-bootstrap-")
        
        try:
            # Convert API git auth config to bootstrap generator config
            bootstrap_git_auth = self._convert_git_auth(request.git_auth)
            
            generator = RepoGenerator(
                output_dir=temp_dir,
                cluster_name=request.cluster_name,
                repo_url=request.repo_url,
                branch=request.branch,
                vendor_charts=False,
                git_auth=bootstrap_git_auth,
                skip_git_push=request.skip_git_push,
                cni_bootstrap_component=request.cni_bootstrap,
                dns_bootstrap_component=request.dns_bootstrap,
                bundle_config=request.bundle_config
            )
            
            repo_path = generator.generate(selected)
            
            # Store session
            storage = get_storage()
            session = storage.create_session(
                config={
                    "cluster_name": request.cluster_name,
                    "repo_url": request.repo_url,
                    "branch": request.branch,
                    "helm_charts": helm_charts_info
                },
                content_path=Path(repo_path),
                ttl_minutes=settings.session_ttl_minutes,
                one_time=True
            )
            
            return {
                "token": session.token,
                "curl_command": f"curl -sSL /bootstrap/{session.token} | bash",
                "expires_in_minutes": settings.session_ttl_minutes,
                "one_time": True
            }
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def create_update(
        self,
        request: GenerateRequest
    ) -> Dict[str, Any]:
        """
        Create an update session for existing installations.
        
        Returns dict with: token, curl_command, expires_in_minutes, one_time, files_count, charts_count
        """
        selected, helm_charts_info, _ = self.process_request(
            request, validate_yaml=False
        )
        
        temp_dir = tempfile.mkdtemp(prefix="k8s-bootstrap-update-")
        
        try:
            bootstrap_git_auth = self._convert_git_auth(request.git_auth)
            
            generator = RepoGenerator(
                output_dir=temp_dir,
                cluster_name=request.cluster_name,
                repo_url=request.repo_url,
                branch=request.branch,
                vendor_charts=False,
                git_auth=bootstrap_git_auth,
                skip_git_push=request.skip_git_push,
                cni_bootstrap_component=request.cni_bootstrap,
                dns_bootstrap_component=request.dns_bootstrap,
                bundle_config=request.bundle_config
            )
            
            repo_path = generator.generate(selected)
            
            # Collect files with checksums
            files_with_checksums = self._collect_files_with_checksums(Path(repo_path))
            
            # Generate update script
            update_gen = UpdateGenerator(
                cluster_name=request.cluster_name,
                repo_url=request.repo_url,
                branch=request.branch,
                git_auth_enabled=request.git_auth.enabled if request.git_auth else False,
                git_platform=request.git_auth.platform if request.git_auth else "github"
            )
            
            update_script = update_gen.generate_update_script(
                new_files=files_with_checksums,
                helm_charts=helm_charts_info
            )
            
            # Store session
            storage = get_storage()
            session = storage.create_session(
                config={
                    "cluster_name": request.cluster_name,
                    "repo_url": request.repo_url,
                    "branch": request.branch,
                    "is_update": True,
                    "update_script": update_script,
                },
                content_path=Path(repo_path),
                ttl_minutes=settings.session_ttl_minutes,
                one_time=True
            )
            
            return {
                "token": session.token,
                "curl_command": f"curl -sSL /update/{session.token} | bash",
                "expires_in_minutes": settings.session_ttl_minutes,
                "one_time": True,
                "files_count": len(files_with_checksums),
                "charts_count": len(helm_charts_info)
            }
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def get_bootstrap_script(self, token: str) -> Optional[str]:
        """Get bootstrap script by token"""
        from app.services.script_generator import ScriptGenerator
        
        storage = get_storage()
        session = storage.get_session(token, mark_accessed=True)
        
        if not session:
            return None
        
        return ScriptGenerator.generate_bootstrap_script(
            content_path=session.content_path,
            cluster_name=session.config.get("cluster_name", "k8s-cluster"),
            repo_url=session.config.get("repo_url", ""),
            branch=session.config.get("branch", "main"),
            helm_charts=session.config.get("helm_charts", [])
        )
    
    def get_update_script(self, token: str) -> Optional[str]:
        """Get update script by token"""
        storage = get_storage()
        session = storage.get_session(token, mark_accessed=True)
        
        if not session:
            return None
        
        return session.config.get("update_script")
    
    @staticmethod
    def _convert_git_auth(git_auth: Optional[GitAuthConfig]) -> Optional[BootstrapGitAuthConfig]:
        """Convert API GitAuthConfig to BootstrapGitAuthConfig"""
        if not git_auth or not git_auth.enabled:
            return None
        
        return BootstrapGitAuthConfig(
            enabled=True,
            platform=git_auth.platform,
            custom_url=git_auth.customUrl,
            username=git_auth.username,
            password=git_auth.password
        )
    
    @staticmethod
    def _collect_files_with_checksums(content_path: Path) -> List[Dict[str, Any]]:
        """Collect all files from content path with their checksums"""
        files = []
        
        for root, dirs, filenames in os.walk(content_path):
            rel_root = Path(root).relative_to(content_path)
            
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = rel_root / filename
                
                # Skip vendored chart files
                parts = rel_path.parts
                if len(parts) >= 4 and parts[0] == "charts" and parts[2] == "charts":
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    continue
                
                is_executable = os.access(file_path, os.X_OK)
                
                files.append({
                    'path': str(rel_path),
                    'content': content,
                    'checksum': calculate_file_checksum(content),
                    'executable': is_executable
                })
        
        return files
