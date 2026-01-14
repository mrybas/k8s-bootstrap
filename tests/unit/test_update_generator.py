"""
Unit tests for UpdateGenerator
"""
import pytest
from pathlib import Path

from app.generator.update_generator import UpdateGenerator, calculate_file_checksum


class TestCalculateFileChecksum:
    """Tests for file checksum calculation"""
    
    def test_same_content_same_checksum(self):
        """Same content should produce same checksum"""
        content = "hello world"
        assert calculate_file_checksum(content) == calculate_file_checksum(content)
    
    def test_different_content_different_checksum(self):
        """Different content should produce different checksum"""
        assert calculate_file_checksum("hello") != calculate_file_checksum("world")
    
    def test_empty_content(self):
        """Empty content should produce valid checksum"""
        checksum = calculate_file_checksum("")
        assert checksum
        assert len(checksum) == 32  # MD5 hex length
    
    def test_unicode_content(self):
        """Unicode content should work"""
        checksum = calculate_file_checksum("привіт світ")
        assert checksum
        assert len(checksum) == 32


class TestUpdateGenerator:
    """Tests for UpdateGenerator class"""
    
    def test_init(self):
        """Test generator initialization"""
        gen = UpdateGenerator(
            cluster_name="test-cluster",
            repo_url="https://github.com/test/repo.git",
            branch="main"
        )
        
        assert gen.cluster_name == "test-cluster"
        assert gen.repo_url == "https://github.com/test/repo.git"
        assert gen.branch == "main"
        assert gen.git_auth_enabled is False
    
    def test_init_with_auth(self):
        """Test generator initialization with auth"""
        gen = UpdateGenerator(
            cluster_name="test-cluster",
            repo_url="https://github.com/test/repo.git",
            branch="main",
            git_auth_enabled=True,
            git_platform="gitlab"
        )
        
        assert gen.git_auth_enabled is True
        assert gen.git_platform == "gitlab"
    
    def test_generate_update_script(self):
        """Test update script generation"""
        gen = UpdateGenerator(
            cluster_name="test-cluster",
            repo_url="https://github.com/test/repo.git",
            branch="main"
        )
        
        files = [
            {
                "path": "charts/test/Chart.yaml",
                "content": "name: test\nversion: 1.0.0",
                "checksum": "abc123",
                "executable": False
            }
        ]
        
        charts = [
            {
                "id": "ingress-nginx",
                "name": "ingress-nginx",
                "version": "4.14.1",
                "repository": "https://kubernetes.github.io/ingress-nginx"
            }
        ]
        
        script = gen.generate_update_script(files, charts)
        
        # Verify script contains expected sections
        assert "#!/usr/bin/env bash" in script
        assert "test-cluster" in script
        assert "github.com/test/repo.git" in script
        assert "check_prerequisites" in script
        assert "sync_git" in script
        assert "check_file_changes" in script
        assert "check_chart_changes" in script
        assert "update_files" in script
        assert "update_charts" in script
        assert "commit_and_push" in script
        assert "trigger_reconciliation" in script
    
    def test_generate_update_script_with_executable(self):
        """Test update script with executable files"""
        gen = UpdateGenerator(
            cluster_name="test-cluster",
            repo_url="https://github.com/test/repo.git",
            branch="main"
        )
        
        files = [
            {
                "path": "bootstrap.sh",
                "content": "#!/bin/bash\necho 'test'",
                "checksum": "abc123",
                "executable": True
            }
        ]
        
        script = gen.generate_update_script(files, [])
        
        assert "bootstrap.sh" in script
        assert "true" in script  # is_executable flag
    
    def test_generate_update_script_empty_charts(self):
        """Test update script with no charts"""
        gen = UpdateGenerator(
            cluster_name="test-cluster",
            repo_url="https://github.com/test/repo.git",
            branch="main"
        )
        
        files = [
            {
                "path": "README.md",
                "content": "# Test",
                "checksum": "abc123",
                "executable": False
            }
        ]
        
        script = gen.generate_update_script(files, [])
        
        assert "README.md" in script
        # Should still have chart check functions (they'll just report 0 charts)
        assert "check_chart_changes" in script
    
    def test_generate_update_script_with_git_auth(self):
        """Test update script with authentication"""
        gen = UpdateGenerator(
            cluster_name="test-cluster",
            repo_url="https://github.com/test/repo.git",
            branch="main",
            git_auth_enabled=True,
            git_platform="github"
        )
        
        script = gen.generate_update_script([], [])
        
        assert "GIT_AUTH_ENABLED=\"true\"" in script
        assert "GIT_PLATFORM=\"github\"" in script


class TestUpdateScriptContent:
    """Tests for update script content quality"""
    
    @pytest.fixture
    def basic_script(self):
        """Generate a basic update script"""
        gen = UpdateGenerator(
            cluster_name="my-cluster",
            repo_url="https://github.com/user/repo.git",
            branch="main"
        )
        
        files = [
            {
                "path": "charts/cert-manager/Chart.yaml",
                "content": "name: cert-manager\nversion: 1.0.0",
                "checksum": "a1b2c3",
                "executable": False
            },
            {
                "path": "bootstrap.sh",
                "content": "#!/bin/bash\necho 'bootstrap'",
                "checksum": "d4e5f6",
                "executable": True
            }
        ]
        
        charts = [
            {
                "id": "cert-manager",
                "name": "cert-manager",
                "version": "1.19.2",
                "repository": "https://charts.jetstack.io"
            }
        ]
        
        return gen.generate_update_script(files, charts)
    
    def test_script_has_shebang(self, basic_script):
        """Script should start with shebang"""
        assert basic_script.startswith("#!/usr/bin/env bash")
    
    def test_script_has_set_options(self, basic_script):
        """Script should set strict bash options"""
        assert "set -euo pipefail" in basic_script
    
    def test_script_has_help_option(self, basic_script):
        """Script should have help option"""
        assert "-h|--help" in basic_script
    
    def test_script_has_dry_run_option(self, basic_script):
        """Script should have dry-run option"""
        assert "-d|--dry-run" in basic_script or "DRY_RUN" in basic_script
    
    def test_script_has_force_option(self, basic_script):
        """Script should have force option"""
        assert "-f|--force" in basic_script or "FORCE" in basic_script
    
    def test_script_checks_prerequisites(self, basic_script):
        """Script should check prerequisites"""
        assert "check_prerequisites" in basic_script
        assert "bootstrap.sh" in basic_script  # Should check for existing bootstrap
        assert "charts" in basic_script  # Should check for charts dir
    
    def test_script_checks_git(self, basic_script):
        """Script should check git status"""
        assert ".git" in basic_script
    
    def test_script_triggers_flux_reconciliation(self, basic_script):
        """Script should trigger Flux reconciliation"""
        assert "trigger_reconciliation" in basic_script
        assert "flux-system" in basic_script
        assert "reconcile.fluxcd.io" in basic_script
    
    def test_script_shows_summary(self, basic_script):
        """Script should show update summary"""
        assert "Update Summary" in basic_script or "summary" in basic_script.lower()
