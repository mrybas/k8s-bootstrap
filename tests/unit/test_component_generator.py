"""
Unit tests for component_generator.py
"""
import pytest
import tempfile
from pathlib import Path

# component_generator is imported via PYTHONPATH which includes /app/scripts
import component_generator


class TestCategoryManagement:
    """Tests for category loading and management."""
    
    def test_load_categories_from_file(self, tmp_path):
        """Test loading categories from YAML file."""
        categories_file = tmp_path / "categories.yaml"
        categories_file.write_text("""
categories:
  ingress:
    name: Ingress
    icon: "🌐"
    description: Ingress controllers
  security:
    name: Security
    icon: "🔐"
    description: Security tools
""")
        
        categories = component_generator.load_categories(tmp_path)
        
        assert "ingress" in categories
        assert categories["ingress"]["name"] == "Ingress"
        assert categories["ingress"]["icon"] == "🌐"
        assert "security" in categories
    
    def test_load_categories_fallback(self, tmp_path):
        """Test fallback when categories file doesn't exist."""
        categories = component_generator.load_categories(tmp_path)
        
        assert "apps" in categories
        assert categories["apps"]["name"] == "Apps"


class TestIconGuessing:
    """Tests for icon guessing logic."""
    
    @pytest.mark.parametrize("name,expected_icon", [
        ("ingress-nginx", "🌐"),
        ("cert-manager", "🔐"),
        ("prometheus", "📊"),
        ("metrics-server", "📈"),
        ("longhorn", "💾"),
        ("external-dns", "🌍"),
        ("flux-system", "🔄"),
        ("cluster-autoscaler", "📈"),
        ("metallb", "🔧"),
        ("unknown-component", "📦"),  # Default
    ])
    def test_guess_icon(self, name, expected_icon):
        """Test icon guessing based on component name."""
        icon = component_generator.guess_icon(name, {})
        assert icon == expected_icon


class TestCategoryGuessing:
    """Tests for category guessing logic."""
    
    @pytest.fixture
    def categories(self):
        return {
            "ingress": {"name": "Ingress"},
            "security": {"name": "Security"},
            "observability": {"name": "Observability"},
            "storage": {"name": "Storage"},
            "system": {"name": "System"},
            "apps": {"name": "Apps"},
        }
    
    @pytest.mark.parametrize("name,description,expected_category", [
        ("ingress-nginx", "NGINX ingress controller", "ingress"),
        ("cert-manager", "Certificate management", "security"),
        ("prometheus", "Monitoring and alerting", "observability"),
        ("loki-stack", "Log aggregation", "observability"),
        ("longhorn", "Cloud native storage", "storage"),
        ("velero", "Backup and restore", "storage"),
        ("external-dns", "DNS management", "system"),
        ("cluster-autoscaler", "Auto scaling", "system"),
        ("my-custom-app", "Custom application", "apps"),  # Default
    ])
    def test_guess_category(self, categories, name, description, expected_category):
        """Test category guessing based on name and description."""
        category = component_generator.guess_category(name, description, categories)
        assert category == expected_category


class TestSchemaGeneration:
    """Tests for JSON schema and UI schema generation."""
    
    def test_infer_schema_type_string(self):
        """Test string type inference."""
        schema = component_generator.infer_schema_type("hello")
        assert schema["type"] == "string"
        assert schema["default"] == "hello"
    
    def test_infer_schema_type_integer(self):
        """Test integer type inference."""
        schema = component_generator.infer_schema_type(42)
        assert schema["type"] == "integer"
        assert schema["default"] == 42
    
    def test_infer_schema_type_boolean(self):
        """Test boolean type inference."""
        schema = component_generator.infer_schema_type(True)
        assert schema["type"] == "boolean"
        assert schema["default"] is True
    
    def test_infer_schema_type_array(self):
        """Test array type inference."""
        schema = component_generator.infer_schema_type(["a", "b"])
        assert schema["type"] == "array"
        assert schema["items"]["type"] == "string"
    
    def test_infer_schema_type_object(self):
        """Test object type inference."""
        schema = component_generator.infer_schema_type({"key": "value"})
        assert schema["type"] == "object"
        assert "properties" in schema
        assert schema["properties"]["key"]["type"] == "string"
    
    def test_generate_json_schema(self):
        """Test JSON schema generation from Helm values."""
        values = {
            "replicaCount": 3,
            "enabled": True,
            "image": {"repository": "nginx", "tag": "latest"},
            "service": {"type": "ClusterIP", "port": 80},
        }
        
        schema = component_generator.generate_json_schema(values)
        
        assert schema["type"] == "object"
        assert "replicaCount" in schema["properties"]
        assert "enabled" in schema["properties"]
        assert "image" in schema["properties"]
        assert "service" in schema["properties"]
        # Resources should be added by default
        assert "resources" in schema["properties"]
    
    def test_generate_ui_schema(self):
        """Test UI schema generation."""
        json_schema = {
            "type": "object",
            "properties": {
                "replicaCount": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "resources": {"type": "object"},
            }
        }
        
        ui_schema = component_generator.generate_ui_schema(json_schema)
        
        assert ui_schema["replicaCount"]["ui:widget"] == "updown"
        assert ui_schema["resources"]["ui:collapsed"] is True


class TestComponentYAMLGeneration:
    """Tests for component YAML generation."""
    
    def test_generate_component_yaml_minimal(self):
        """Test minimal component YAML generation."""
        categories = {
            "apps": {"name": "Apps", "icon": "📦", "description": "Applications"}
        }
        
        yaml_content = component_generator.generate_component_yaml(
            component_id="test-app",
            repo_url="https://charts.example.com",
            chart_name="test-app",
            version="1.0.0",
            category="apps",
            categories=categories,
            fetch_values=False  # Don't fetch from real repo
        )
        
        assert "id: test-app" in yaml_content
        assert "name: Test App" in yaml_content
        assert "category: apps" in yaml_content
        assert "chartType: upstream" in yaml_content
        assert "repository: https://charts.example.com" in yaml_content
        assert 'version: "1.0.0"' in yaml_content
    
    def test_generate_component_yaml_with_options(self):
        """Test component YAML with custom options."""
        categories = {
            "security": {"name": "Security", "icon": "🔐", "description": "Security tools"}
        }
        
        yaml_content = component_generator.generate_component_yaml(
            component_id="my-vault",
            repo_url="https://helm.releases.hashicorp.com",
            chart_name="vault",
            version="0.25.0",
            category="security",
            categories=categories,
            name="HashiCorp Vault",
            description="Secrets management",
            namespace="vault-system",
            icon="🔐",
            docs_url="https://www.vaultproject.io/docs",
            fetch_values=False
        )
        
        assert "id: my-vault" in yaml_content
        assert "name: HashiCorp Vault" in yaml_content
        assert "description: Secrets management" in yaml_content
        assert "namespace: vault-system" in yaml_content
        assert "docsUrl: https://www.vaultproject.io/docs" in yaml_content


class TestCLIMode:
    """Tests for CLI mode functionality."""
    
    def test_cli_generate_to_file(self, tmp_path):
        """Test generating component via CLI to file."""
        output_file = tmp_path / "test-component.yaml"
        
        # Mock the definitions path
        original_func = component_generator.get_definitions_path
        component_generator.get_definitions_path = lambda: tmp_path
        
        # Create categories file
        (tmp_path / "categories.yaml").write_text("""
categories:
  apps:
    name: Apps
    icon: "📦"
    description: Applications
""")
        
        try:
            yaml_content = component_generator.generate_component_yaml(
                component_id="cli-test",
                repo_url="https://example.com/charts",
                chart_name="cli-test",
                version="1.0.0",
                category="apps",
                categories={"apps": {"name": "Apps", "icon": "📦", "description": ""}},
                fetch_values=False
            )
            
            output_file.write_text(yaml_content)
            
            assert output_file.exists()
            content = output_file.read_text()
            assert "id: cli-test" in content
            
        finally:
            component_generator.get_definitions_path = original_func
    
    def test_cli_print_mode(self, capsys):
        """Test printing component to stdout."""
        yaml_content = component_generator.generate_component_yaml(
            component_id="stdout-test",
            repo_url="https://example.com",
            chart_name="stdout-test",
            version="1.0.0",
            category="apps",
            categories={"apps": {"name": "Apps", "icon": "📦", "description": ""}},
            fetch_values=False
        )
        
        print(yaml_content)
        captured = capsys.readouterr()
        
        assert "id: stdout-test" in captured.out


class TestCategoryPersistence:
    """Tests for category save functionality."""
    
    def test_save_categories(self, tmp_path):
        """Test saving new categories to file."""
        categories = {
            "ingress": {"name": "Ingress", "icon": "🌐", "description": "Ingress controllers"},
            "new-cat": {"name": "New Category", "icon": "🆕", "description": "Brand new"}
        }
        
        component_generator.save_categories(categories, tmp_path)
        
        # Verify file was created
        categories_file = tmp_path / "categories.yaml"
        assert categories_file.exists()
        
        # Reload and verify
        loaded = component_generator.load_categories(tmp_path)
        assert "ingress" in loaded
        assert "new-cat" in loaded
        assert loaded["new-cat"]["name"] == "New Category"
