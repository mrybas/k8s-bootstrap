"""
Unit tests for component definitions.

These tests validate that all component definition YAML files are:
- Syntactically correct
- Have required fields
- Have valid references (dependencies, operators, etc.)
- Follow naming conventions
"""
import pytest
import yaml
from pathlib import Path
from typing import Dict, List, Set
from jsonschema import validate, ValidationError


# Path to definitions
DEFINITIONS_PATH = Path(__file__).parent.parent.parent / "backend" / "definitions" / "components"


# JSON Schema for component definitions
COMPONENT_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "category", "description"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[a-z0-9-]+$",
            "description": "Unique identifier (lowercase, hyphens only)"
        },
        "name": {"type": "string", "minLength": 1},
        "category": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 10},
        "docsUrl": {"type": "string", "format": "uri"},
        "hidden": {"type": "boolean"},
        "alwaysInclude": {"type": "boolean"},
        "autoGenerate": {"type": "boolean"},
        "isOperator": {"type": "boolean"},
        "operatorFor": {"type": "string"},
        "isInstance": {"type": "boolean"},
        "instanceOf": {"type": "string"},
        "suggestsInstances": {"type": "array", "items": {"type": "string"}},
        "suggestsComponents": {"type": "array", "items": {"type": "string"}},
        "chartType": {
            "type": "string",
            "enum": ["upstream", "custom", "meta"]
        },
        "multiInstance": {"type": "boolean"},
        "requiresOperator": {"type": "string"},
        "autoIncludes": {"type": "array", "items": {"type": "string"}},
        "autoInclude": {"type": "object"},
        "upstream": {
            "type": "object",
            "properties": {
                "repository": {"type": "string"},
                "chartName": {"type": "string"},
                "version": {"type": "string"}
            },
            "required": ["repository", "chartName", "version"]
        },
        "namespace": {"type": "string"},
        "releaseName": {"type": "string"},
        "createNamespace": {"type": "boolean"},
        "priority": {"type": "integer", "minimum": 0},
        "timeout": {"type": "string"},
        "dependencies": {"type": "array", "items": {"type": "string"}},
        "requiresCrds": {"type": "array", "items": {"type": "string"}},
        "defaultValues": {"type": "object"},
        "formSchema": {"type": "object"},
        "templates": {"type": "object"}
    },
    "additionalProperties": True
}


def load_all_definitions() -> Dict[str, Dict]:
    """Load all component definitions from YAML files."""
    definitions = {}
    for yaml_file in DEFINITIONS_PATH.glob("*.yaml"):
        with open(yaml_file) as f:
            try:
                data = yaml.safe_load(f)
                if data and "id" in data:
                    definitions[data["id"]] = {"data": data, "file": yaml_file.name}
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in {yaml_file.name}: {e}")
    return definitions


def get_all_definition_ids() -> List[str]:
    """Get list of all definition IDs for parametrization."""
    return list(load_all_definitions().keys())


# Load definitions once for all tests
ALL_DEFINITIONS = load_all_definitions()


class TestDefinitionSyntax:
    """Test that all definitions are syntactically correct."""
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_yaml_is_valid(self, def_id: str):
        """Test that YAML file is valid."""
        assert def_id in ALL_DEFINITIONS
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_matches_schema(self, def_id: str):
        """Test that definition matches JSON schema."""
        definition = ALL_DEFINITIONS[def_id]["data"]
        filename = ALL_DEFINITIONS[def_id]["file"]
        
        try:
            validate(instance=definition, schema=COMPONENT_SCHEMA)
        except ValidationError as e:
            pytest.fail(f"{filename}: Schema validation failed - {e.message}")
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_id_matches_filename(self, def_id: str):
        """Test that component ID matches filename."""
        filename = ALL_DEFINITIONS[def_id]["file"]
        expected_filename = f"{def_id}.yaml"
        assert filename == expected_filename, \
            f"ID '{def_id}' doesn't match filename '{filename}'"


class TestDefinitionRequirements:
    """Test that definitions have required content."""
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_visible_components_have_docs_url(self, def_id: str):
        """Test that non-hidden components have documentation URL."""
        definition = ALL_DEFINITIONS[def_id]["data"]
        
        if not definition.get("hidden") and not definition.get("alwaysInclude"):
            assert "docsUrl" in definition, \
                f"Visible component '{def_id}' missing docsUrl"
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_upstream_charts_have_upstream_config(self, def_id: str):
        """Test that upstream charts have upstream configuration."""
        definition = ALL_DEFINITIONS[def_id]["data"]
        
        if definition.get("chartType") == "upstream":
            assert "upstream" in definition, \
                f"Upstream chart '{def_id}' missing upstream config"
            upstream = definition["upstream"]
            assert "repository" in upstream, f"'{def_id}' missing upstream.repository"
            assert "chartName" in upstream, f"'{def_id}' missing upstream.chartName"
            assert "version" in upstream, f"'{def_id}' missing upstream.version"
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_has_namespace(self, def_id: str):
        """Test that components specify a namespace."""
        definition = ALL_DEFINITIONS[def_id]["data"]
        
        # Skip hidden/auto-generated components that might not need namespace
        if definition.get("autoGenerate"):
            return
        
        # Skip meta-components (they don't deploy directly)
        if definition.get("chartType") == "meta":
            return
        
        assert "namespace" in definition, \
            f"Component '{def_id}' missing namespace"
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_instance_has_operator(self, def_id: str):
        """Test that instance components specify their operator."""
        definition = ALL_DEFINITIONS[def_id]["data"]
        
        if definition.get("isInstance"):
            assert "instanceOf" in definition, \
                f"Instance '{def_id}' missing instanceOf field"
            assert definition["instanceOf"] in ALL_DEFINITIONS, \
                f"Instance '{def_id}' references non-existent operator '{definition['instanceOf']}'"


class TestDefinitionReferences:
    """Test that all references between definitions are valid."""
    
    def test_all_dependencies_exist(self):
        """Test that all declared dependencies exist."""
        for def_id, info in ALL_DEFINITIONS.items():
            definition = info["data"]
            for dep in definition.get("dependencies", []):
                assert dep in ALL_DEFINITIONS, \
                    f"'{def_id}' depends on non-existent component '{dep}'"
    
    def test_all_required_crds_exist(self):
        """Test that all requiresCrds references exist."""
        for def_id, info in ALL_DEFINITIONS.items():
            definition = info["data"]
            for crd in definition.get("requiresCrds", []):
                assert crd in ALL_DEFINITIONS, \
                    f"'{def_id}' requires non-existent CRD component '{crd}'"
    
    def test_all_instance_of_references_exist(self):
        """Test that all instanceOf references exist."""
        for def_id, info in ALL_DEFINITIONS.items():
            definition = info["data"]
            if "instanceOf" in definition:
                operator = definition["instanceOf"]
                assert operator in ALL_DEFINITIONS, \
                    f"'{def_id}' instanceOf non-existent operator '{operator}'"
                # Verify the referenced component is actually an operator
                assert ALL_DEFINITIONS[operator]["data"].get("isOperator"), \
                    f"'{def_id}' references '{operator}' which is not an operator"
    
    def test_all_suggested_instances_exist(self):
        """Test that all suggestsInstances references exist."""
        for def_id, info in ALL_DEFINITIONS.items():
            definition = info["data"]
            for instance in definition.get("suggestsInstances", []):
                assert instance in ALL_DEFINITIONS, \
                    f"'{def_id}' suggests non-existent instance '{instance}'"
    
    def test_all_suggested_components_exist(self):
        """Test that all suggestsComponents references exist."""
        for def_id, info in ALL_DEFINITIONS.items():
            definition = info["data"]
            for comp in definition.get("suggestsComponents", []):
                assert comp in ALL_DEFINITIONS, \
                    f"'{def_id}' suggests non-existent component '{comp}'"
    
    def test_no_circular_dependencies(self):
        """Test that there are no circular dependencies."""
        def find_cycle(start: str, visited: Set[str], path: List[str]) -> List[str]:
            if start in visited:
                cycle_start = path.index(start)
                return path[cycle_start:] + [start]
            
            visited.add(start)
            path.append(start)
            
            deps = ALL_DEFINITIONS[start]["data"].get("dependencies", [])
            for dep in deps:
                if dep in ALL_DEFINITIONS:
                    cycle = find_cycle(dep, visited.copy(), path.copy())
                    if cycle:
                        return cycle
            
            return []
        
        for def_id in ALL_DEFINITIONS:
            cycle = find_cycle(def_id, set(), [])
            assert not cycle, \
                f"Circular dependency detected: {' -> '.join(cycle)}"


class TestNamespaceStrategy:
    """Test namespace strategy follows project conventions."""
    
    def test_crd_charts_use_cluster_crds_namespace(self):
        """Test that CRD charts use cluster-crds namespace."""
        crd_components = [
            def_id for def_id, info in ALL_DEFINITIONS.items()
            if def_id.endswith("-crds")
        ]
        
        for def_id in crd_components:
            definition = ALL_DEFINITIONS[def_id]["data"]
            ns = definition.get("namespace")
            assert ns == "cluster-crds", \
                f"CRD chart '{def_id}' should use namespace 'cluster-crds', got '{ns}'"
    
    def test_flux_components_use_flux_system_namespace(self):
        """Test that flux-operator and flux-instance use flux-system namespace."""
        flux_components = ["flux-operator", "flux-instance"]
        
        for def_id in flux_components:
            if def_id in ALL_DEFINITIONS:
                definition = ALL_DEFINITIONS[def_id]["data"]
                ns = definition.get("namespace")
                assert ns == "flux-system", \
                    f"Flux component '{def_id}' should use namespace 'flux-system', got '{ns}'"
    
    def test_regular_components_have_dedicated_namespaces(self):
        """Test that regular components have their own dedicated namespaces."""
        # Components that should NOT use kube-system
        should_have_own_namespace = [
            "metrics-server", "vertical-pod-autoscaler", "coredns", "cluster-autoscaler"
        ]
        
        for def_id in should_have_own_namespace:
            if def_id in ALL_DEFINITIONS:
                definition = ALL_DEFINITIONS[def_id]["data"]
                ns = definition.get("namespace")
                assert ns != "kube-system", \
                    f"Component '{def_id}' should have its own namespace, not 'kube-system'"


class TestDefinitionConsistency:
    """Test consistency across definitions."""
    
    def test_unique_ids(self):
        """Test that all component IDs are unique."""
        ids = [info["data"]["id"] for info in ALL_DEFINITIONS.values()]
        assert len(ids) == len(set(ids)), "Duplicate component IDs found"
    
    def test_unique_release_names_per_namespace(self):
        """Test that release names are unique within each namespace."""
        releases_by_ns = {}
        for def_id, info in ALL_DEFINITIONS.items():
            definition = info["data"]
            ns = definition.get("namespace", "default")
            release = definition.get("releaseName", def_id)
            
            if ns not in releases_by_ns:
                releases_by_ns[ns] = {}
            
            assert release not in releases_by_ns[ns], \
                f"Duplicate release name '{release}' in namespace '{ns}': " \
                f"'{def_id}' and '{releases_by_ns[ns].get(release)}'"
            
            releases_by_ns[ns][release] = def_id
    
    def test_operators_have_suggested_instances(self):
        """Test that operators suggest their instances (optional but good practice)."""
        operators = [
            (def_id, info["data"])
            for def_id, info in ALL_DEFINITIONS.items()
            if info["data"].get("isOperator")
        ]
        
        for def_id, definition in operators:
            # This is a soft check - just print warning
            if not definition.get("suggestsInstances"):
                print(f"Note: Operator '{def_id}' has no suggestsInstances")
    
    def test_categories_are_consistent(self):
        """Test that categories follow a standard set."""
        expected_categories = {
            "core", "crds", "ingress", "security", "observability", 
            "storage", "gitops", "system", "apps", "backup"
        }
        
        found_categories = set()
        for info in ALL_DEFINITIONS.values():
            found_categories.add(info["data"]["category"])
        
        # Just report unexpected categories, don't fail
        unexpected = found_categories - expected_categories
        if unexpected:
            print(f"Note: Found unexpected categories: {unexpected}")


class TestFormSchema:
    """Test form schema definitions for UI rendering."""
    
    @pytest.mark.parametrize("def_id", get_all_definition_ids())
    def test_form_schema_has_valid_types(self, def_id: str):
        """Test that form schema uses valid field types."""
        definition = ALL_DEFINITIONS[def_id]["data"]
        form_schema = definition.get("formSchema", {})
        
        valid_types = {"text", "number", "boolean", "select", "password", "textarea", "object", "array"}
        
        def check_field(field: dict, path: str):
            if "type" in field:
                assert field["type"] in valid_types, \
                    f"'{def_id}' has invalid form field type at {path}: {field['type']}"
            
            # Recursively check nested fields
            for key, value in field.get("properties", {}).items():
                check_field(value, f"{path}.{key}")
        
        for section_name, section in form_schema.items():
            for field_name, field in section.get("fields", {}).items():
                check_field(field, f"{section_name}.{field_name}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
