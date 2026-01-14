"""
Jinja2 template engine for generating Kubernetes manifests and scripts
"""
from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape
import yaml

# Templates are in app/templates/ (relative to app package)
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _yaml_filter(data: Any, default_flow_style: bool = False) -> str:
    """Convert Python object to YAML string"""
    return yaml.dump(data, default_flow_style=default_flow_style, sort_keys=False)


def _indent_filter(text: str, width: int = 4, first: bool = False) -> str:
    """Indent text by given width"""
    indent = ' ' * width
    lines = text.split('\n')
    if first:
        return '\n'.join(indent + line if line else line for line in lines)
    else:
        return lines[0] + '\n' + '\n'.join(indent + line if line else line for line in lines[1:])


def create_jinja_env() -> Environment:
    """Create and configure Jinja2 environment"""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    
    # Custom filters
    env.filters['to_yaml'] = _yaml_filter
    env.filters['indent'] = _indent_filter
    
    return env


# Singleton environment
_env: Environment = None


def get_env() -> Environment:
    """Get or create Jinja2 environment"""
    global _env
    if _env is None:
        _env = create_jinja_env()
    return _env


def render(template_path: str, **context) -> str:
    """
    Render a template with given context
    
    Args:
        template_path: Path to template relative to templates/ directory
        **context: Variables to pass to template
        
    Returns:
        Rendered template string
    """
    return get_env().get_template(template_path).render(**context)


def render_to_file(template_path: str, output_path: Path, **context) -> None:
    """
    Render a template and write to file
    
    Args:
        template_path: Path to template relative to templates/ directory
        output_path: Path to output file
        **context: Variables to pass to template
    """
    content = render(template_path, **context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
