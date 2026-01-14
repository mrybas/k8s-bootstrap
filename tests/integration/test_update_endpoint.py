"""
Integration tests for Update API endpoint
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestUpdateEndpoint:
    """Tests for /api/update endpoint"""
    
    def test_create_update_success(self):
        """Test successful update creation"""
        response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert "curl_command" in data
        assert "expires_in_minutes" in data
        assert "one_time" in data
        assert "files_count" in data
        assert "charts_count" in data
        
        assert data["files_count"] > 0
        assert data["one_time"] is True
    
    def test_create_update_invalid_cluster_name(self):
        """Test update with invalid cluster name"""
        response = client.post("/api/update", json={
            "cluster_name": "invalid name with spaces!",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        assert response.status_code == 400
        assert "Invalid cluster name" in response.json()["detail"]
    
    def test_create_update_no_components(self):
        """Test update with no components selected"""
        response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": []
        })
        
        assert response.status_code == 400
        assert "No components selected" in response.json()["detail"]
    
    def test_create_update_with_auth(self):
        """Test update with git authentication"""
        response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://gitlab.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "ingress-nginx", "enabled": True, "values": {}, "raw_overrides": ""}
            ],
            "git_auth": {
                "enabled": True,
                "platform": "gitlab",
                "customUrl": "https://gitlab.com"
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"]
    
    def test_get_update_script(self):
        """Test getting update script by token"""
        # First create an update
        create_response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "metrics-server", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        assert create_response.status_code == 200
        token = create_response.json()["token"]
        
        # Get the update script
        script_response = client.get(f"/update/{token}")
        
        assert script_response.status_code == 200
        assert script_response.headers["content-type"] == "text/plain; charset=utf-8"
        
        script = script_response.text
        assert "#!/usr/bin/env bash" in script
        assert "test-cluster" in script
        assert "check_prerequisites" in script
        assert "sync_git" in script
    
    def test_get_update_script_invalid_token(self):
        """Test getting update script with invalid token"""
        response = client.get("/update/invalid-token-123")
        
        assert response.status_code == 404
        assert "Invalid or expired" in response.text
    
    def test_update_script_is_one_time(self):
        """Test that update script can only be retrieved once"""
        # Create an update
        create_response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "metallb", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        token = create_response.json()["token"]
        
        # First access should work
        first_response = client.get(f"/update/{token}")
        assert first_response.status_code == 200
        assert "#!/usr/bin/env bash" in first_response.text
        
        # Second access should fail (one-time use)
        second_response = client.get(f"/update/{token}")
        assert second_response.status_code == 404
        assert "Invalid or expired" in second_response.text


class TestUpdateVsBootstrap:
    """Tests comparing update and bootstrap endpoints"""
    
    def test_update_returns_different_fields(self):
        """Update response has additional fields compared to bootstrap"""
        # Bootstrap
        bootstrap_response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        # Update
        update_response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        bootstrap_data = bootstrap_response.json()
        update_data = update_response.json()
        
        # Both have common fields
        assert "token" in bootstrap_data and "token" in update_data
        assert "curl_command" in bootstrap_data and "curl_command" in update_data
        
        # Update has additional fields
        assert "files_count" in update_data
        assert "charts_count" in update_data
        assert "files_count" not in bootstrap_data
    
    def test_update_script_differs_from_bootstrap(self):
        """Update script content is different from bootstrap script"""
        # Get bootstrap script
        bootstrap_create = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        bootstrap_token = bootstrap_create.json()["token"]
        bootstrap_script = client.get(f"/bootstrap/{bootstrap_token}").text
        
        # Get update script
        update_create = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        update_token = update_create.json()["token"]
        update_script = client.get(f"/update/{update_token}").text
        
        # They should be different
        assert bootstrap_script != update_script
        
        # Update script has unique features
        assert "check_prerequisites" in update_script
        assert "sync_git" in update_script
        assert "trigger_reconciliation" in update_script
        
        # Bootstrap script creates directories
        assert "mkdir -p" in bootstrap_script


class TestUpdateScriptFeatures:
    """Tests for specific update script features"""
    
    @pytest.fixture
    def update_script(self):
        """Get an update script"""
        create_response = client.post("/api/update", json={
            "cluster_name": "test-cluster",
            "repo_url": "https://github.com/test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""},
                {"id": "ingress-nginx", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        token = create_response.json()["token"]
        return client.get(f"/update/{token}").text
    
    def test_has_dry_run_mode(self, update_script):
        """Update script should support dry-run mode"""
        assert "DRY_RUN" in update_script
        assert "--dry-run" in update_script
    
    def test_has_force_mode(self, update_script):
        """Update script should support force mode"""
        assert "FORCE_UPDATE" in update_script
        assert "--force" in update_script
    
    def test_checks_for_existing_installation(self, update_script):
        """Update script should verify it's in a bootstrap directory"""
        assert "bootstrap.sh" in update_script
        assert "charts" in update_script
        assert "manifests" in update_script
    
    def test_compares_checksums(self, update_script):
        """Update script should compare file checksums"""
        assert "checksum" in update_script.lower() or "md5sum" in update_script
    
    def test_handles_git_sync(self, update_script):
        """Update script should sync with git remote"""
        assert "git fetch" in update_script or "sync_git" in update_script
        assert "git pull" in update_script
    
    def test_commits_changes(self, update_script):
        """Update script should commit changes"""
        assert "git add" in update_script
        assert "git commit" in update_script
    
    def test_pushes_changes(self, update_script):
        """Update script should push changes"""
        assert "git push" in update_script
    
    def test_triggers_flux(self, update_script):
        """Update script should trigger Flux reconciliation"""
        assert "flux-system" in update_script
        assert "reconcile" in update_script or "annotate" in update_script
