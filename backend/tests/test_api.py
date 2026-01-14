"""
Tests for the API endpoints
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for health endpoint"""
    
    def test_health_check(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestCategoriesEndpoint:
    """Tests for categories endpoint"""
    
    def test_get_categories(self):
        response = client.get("/api/categories")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        
        # Check structure
        if len(data) > 0:
            category = data[0]
            assert "id" in category
            assert "name" in category
            assert "components" in category
            assert isinstance(category["components"], list)


class TestComponentsEndpoint:
    """Tests for components endpoint"""
    
    def test_get_components(self):
        response = client.get("/api/components")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_component_not_found(self):
        response = client.get("/api/components/nonexistent-component")
        assert response.status_code == 404
    
    def test_get_component_schema(self):
        # First get a valid component ID
        components_response = client.get("/api/components")
        components = components_response.json()
        
        if len(components) > 0:
            comp_id = components[0]["id"]
            response = client.get(f"/api/components/{comp_id}/schema")
            assert response.status_code == 200
            
            data = response.json()
            assert "jsonSchema" in data
            assert "uiSchema" in data
            assert "defaultValues" in data


class TestBootstrapEndpoint:
    """Tests for bootstrap endpoint"""
    
    def test_bootstrap_invalid_cluster_name(self):
        response = client.post("/api/bootstrap", json={
            "cluster_name": "invalid name with spaces!",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}}
            ]
        })
        assert response.status_code == 400
    
    def test_bootstrap_no_components(self):
        response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": []
        })
        assert response.status_code == 400
    
    def test_bootstrap_returns_token(self):
        response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": [
                {"id": "cert-manager", "enabled": True, "values": {}, "raw_overrides": ""}
            ]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "curl_command" in data
    
    def test_bootstrap_invalid_raw_yaml_syntax(self):
        """Test that invalid YAML syntax in raw_overrides is rejected"""
        response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": [
                {
                    "id": "cert-manager", 
                    "enabled": True, 
                    "values": {}, 
                    "raw_overrides": "invalid: yaml: syntax: [unclosed"
                }
            ]
        })
        
        assert response.status_code == 400
        assert "Invalid raw YAML" in response.json()["detail"]
    
    def test_bootstrap_invalid_raw_yaml_not_dict(self):
        """Test that raw_overrides must be a YAML mapping, not a list or scalar"""
        response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": [
                {
                    "id": "cert-manager", 
                    "enabled": True, 
                    "values": {}, 
                    "raw_overrides": "- item1\n- item2"  # List, not dict
                }
            ]
        })
        
        assert response.status_code == 400
        assert "must be a YAML mapping" in response.json()["detail"]
    
    def test_bootstrap_valid_raw_yaml(self):
        """Test that valid YAML in raw_overrides is accepted"""
        response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": [
                {
                    "id": "cert-manager", 
                    "enabled": True, 
                    "values": {}, 
                    "raw_overrides": "installCRDs: true\nreplicas: 2"
                }
            ]
        })
        
        assert response.status_code == 200
    
    def test_bootstrap_empty_raw_yaml(self):
        """Test that empty raw_overrides is accepted"""
        response = client.post("/api/bootstrap", json={
            "cluster_name": "test-cluster",
            "repo_url": "git@github.com:test/repo.git",
            "branch": "main",
            "components": [
                {
                    "id": "cert-manager", 
                    "enabled": True, 
                    "values": {}, 
                    "raw_overrides": "   \n   "  # Whitespace only
                }
            ]
        })
        
        assert response.status_code == 200


class TestPreviewEndpoint:
    """Tests for preview endpoint"""
    
    def test_preview_structure(self):
        response = client.get("/api/preview", params={
            "cluster_name": "test-cluster",
            "components": "namespaces"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "tree" in data
        assert isinstance(data["tree"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
