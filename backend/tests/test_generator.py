"""
Tests for the repository generator
"""
import os
import tempfile
import shutil
from pathlib import Path

import pytest
import yaml

from app.generator.repo_generator import RepoGenerator
from app.generator.chart_generator import ChartGenerator


class TestChartGenerator:
    """Tests for ChartGenerator"""
    
    def setup_method(self):
        self.generator = ChartGenerator()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_custom_chart(self):
        """Test generating a custom chart (namespaces)"""
        definition = {
            "id": "namespaces",
            "name": "Namespaces",
            "chartType": "custom",
            "defaultValues": {
                "namespaces": [
                    {"name": "apps"},
                    {"name": "monitoring"}
                ]
            },
            "templates": {}
        }
        
        chart_path = self.generator.generate_chart(
            definition=definition,
            values={"namespaces": [{"name": "custom-ns"}]},
            raw_overrides="",
            output_dir=Path(self.temp_dir)
        )
        
        # Check Chart.yaml exists
        assert (chart_path / "Chart.yaml").exists()
        
        # Check values.yaml has merged values
        with open(chart_path / "values.yaml") as f:
            values = yaml.safe_load(f)
        
        assert values["namespaces"][0]["name"] == "custom-ns"
        
        # Check templates directory exists
        assert (chart_path / "templates").is_dir()
    
    def test_generate_wrapper_chart(self):
        """Test generating a wrapper chart for upstream dependency"""
        definition = {
            "id": "cert-manager",
            "name": "cert-manager",
            "chartType": "upstream",
            "upstream": {
                "repository": "https://charts.jetstack.io",
                "chartName": "cert-manager",
                "version": "1.14.3"
            },
            "defaultValues": {
                "installCRDs": True
            }
        }
        
        chart_path = self.generator.generate_chart(
            definition=definition,
            values={},
            raw_overrides="",
            output_dir=Path(self.temp_dir)
        )
        
        # Check Chart.yaml exists with dependency
        assert (chart_path / "Chart.yaml").exists()
        with open(chart_path / "Chart.yaml") as f:
            chart = yaml.safe_load(f)
        
        assert chart["name"] == "cert-manager"
        assert "dependencies" in chart
        assert chart["dependencies"][0]["name"] == "cert-manager"
        
        # Check vendored chart directory exists
        assert (chart_path / "charts" / "cert-manager").is_dir()
    
    def test_validate_raw_yaml_valid(self):
        """Test validation of valid YAML"""
        valid_cases = [
            "",
            "   ",
            "key: value",
            "nested:\n  key: value",
            "list_val:\n  - item1\n  - item2",
            "complex:\n  nested:\n    deep: value\n  array:\n    - one\n    - two",
        ]
        
        for yaml_str in valid_cases:
            is_valid, error = ChartGenerator.validate_raw_yaml(yaml_str, "test-component")
            assert is_valid, f"Expected valid for: {repr(yaml_str)}, got error: {error}"
            assert error is None
    
    def test_validate_raw_yaml_invalid_syntax(self):
        """Test validation rejects invalid YAML syntax"""
        invalid_cases = [
            "invalid: yaml: syntax",
            "[unclosed bracket",
            "key: [unclosed",
            "  bad indent\nkey: value",
            "---\nkey: value\n---\ninvalid: yaml:",
        ]
        
        for yaml_str in invalid_cases:
            is_valid, error = ChartGenerator.validate_raw_yaml(yaml_str, "test-component")
            assert not is_valid, f"Expected invalid for: {repr(yaml_str)}"
            assert "Invalid YAML" in error
            assert "test-component" in error
    
    def test_validate_raw_yaml_not_dict(self):
        """Test validation rejects non-dict YAML (lists, scalars)"""
        non_dict_cases = [
            "- item1\n- item2",  # List
            "just a string",     # Scalar string
            "123",               # Scalar number
            "true",              # Scalar boolean
        ]
        
        for yaml_str in non_dict_cases:
            is_valid, error = ChartGenerator.validate_raw_yaml(yaml_str, "my-component")
            assert not is_valid, f"Expected invalid for non-dict: {repr(yaml_str)}"
            assert "must be a YAML mapping" in error
            assert "my-component" in error
    
    def test_merge_with_raw_overrides(self):
        """Test that valid raw overrides are merged correctly"""
        definition = {
            "id": "test",
            "name": "Test",
            "chartType": "custom",
            "defaultValues": {"existing": "value", "nested": {"a": 1}}
        }
        
        chart_path = self.generator.generate_chart(
            definition=definition,
            values={"user": "provided"},
            raw_overrides="nested:\n  b: 2\nnew_key: new_value",
            output_dir=Path(self.temp_dir)
        )
        
        with open(chart_path / "values.yaml") as f:
            values = yaml.safe_load(f)
        
        assert values["existing"] == "value"
        assert values["user"] == "provided"
        assert values["nested"]["a"] == 1
        assert values["nested"]["b"] == 2
        assert values["new_key"] == "new_value"


class TestRepoGenerator:
    """Tests for RepoGenerator"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_full_repository(self):
        """Test generating a complete repository structure"""
        generator = RepoGenerator(
            output_dir=self.temp_dir,
            cluster_name="test-cluster",
            repo_url="git@github.com:test/repo.git",
            branch="main"
        )
        
        components = [
            {
                "definition": {
                    "id": "namespaces",
                    "name": "Namespaces",
                    "chartType": "custom",
                    "namespace": "default",
                    "releaseName": "namespaces",
                    "priority": 1,
                    "createNamespace": False,
                    "defaultValues": {
                        "namespaces": [{"name": "apps"}]
                    }
                },
                "values": {},
                "raw_overrides": ""
            }
        ]
        
        repo_path = generator.generate(components)
        
        # Check directory structure (updated for flux-native pattern)
        assert os.path.exists(repo_path)
        assert os.path.exists(os.path.join(repo_path, "charts"))
        assert os.path.exists(os.path.join(repo_path, "manifests", "infrastructure"))
        assert os.path.exists(os.path.join(repo_path, "bootstrap.sh"))
        assert os.path.exists(os.path.join(repo_path, "README.md"))
        assert os.path.exists(os.path.join(repo_path, ".gitignore"))
        
        # Check bootstrap script is executable
        assert os.access(os.path.join(repo_path, "bootstrap.sh"), os.X_OK)
    
    def test_normalize_name(self):
        """Test name normalization"""
        generator = RepoGenerator(
            output_dir=self.temp_dir,
            cluster_name="Test Cluster_Name",
            repo_url="",
            branch="main"
        )
        
        assert generator.cluster_name == "test-cluster-name"
    
    def test_deterministic_output(self):
        """Test that same input produces same output"""
        components = [
            {
                "definition": {
                    "id": "test",
                    "name": "Test",
                    "chartType": "custom",
                    "namespace": "default",
                    "releaseName": "test",
                    "priority": 1,
                    "createNamespace": False,
                    "defaultValues": {}
                },
                "values": {"key": "value"},
                "raw_overrides": ""
            }
        ]
        
        # Generate twice
        temp1 = tempfile.mkdtemp()
        temp2 = tempfile.mkdtemp()
        
        try:
            gen1 = RepoGenerator(temp1, "cluster", "git@test.git", "main")
            gen2 = RepoGenerator(temp2, "cluster", "git@test.git", "main")
            
            path1 = gen1.generate(components)
            path2 = gen2.generate(components)
            
            # Compare values.yaml content
            with open(os.path.join(path1, "charts", "test", "values.yaml")) as f1:
                content1 = f1.read()
            with open(os.path.join(path2, "charts", "test", "values.yaml")) as f2:
                content2 = f2.read()
            
            assert content1 == content2
        finally:
            shutil.rmtree(temp1, ignore_errors=True)
            shutil.rmtree(temp2, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
