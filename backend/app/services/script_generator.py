"""
Script generation service
"""
import os
from pathlib import Path
from typing import List, Dict, Any


class ScriptGenerator:
    """Service for generating bash scripts"""
    
    @staticmethod
    def generate_bootstrap_script(
        content_path: Path,
        cluster_name: str,
        repo_url: str,
        branch: str,
        helm_charts: List[Dict[str, str]] = None
    ) -> str:
        """
        Generate a self-contained bootstrap script.
        
        Uses:
        - mkdir for directories
        - cat << 'EOF' heredocs for file contents
        - helm repo add + helm pull for charts
        """
        if helm_charts is None:
            helm_charts = []
        
        # Collect files (excluding vendored charts)
        files_to_create = ScriptGenerator._collect_files(content_path, helm_charts)
        
        # Generate sections
        mkdir_section = ScriptGenerator._generate_mkdir_section(files_to_create)
        files_section = ScriptGenerator._generate_files_section(files_to_create)
        helm_section = ScriptGenerator._generate_helm_section(helm_charts)
        
        return ScriptGenerator._render_script(
            cluster_name=cluster_name,
            repo_url=repo_url,
            branch=branch,
            mkdir_section=mkdir_section,
            files_section=files_section,
            helm_section=helm_section
        )
    
    @staticmethod
    def _collect_files(
        content_path: Path, 
        helm_charts: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Collect files from content path"""
        files_to_create = []
        
        for root, dirs, files in os.walk(content_path):
            rel_root = Path(root).relative_to(content_path)
            
            for filename in files:
                file_path = Path(root) / filename
                rel_path = rel_root / filename
                
                # Skip vendored charts if we're using helm pull
                parts = rel_path.parts
                if helm_charts and len(parts) >= 4 and parts[0] == "charts" and parts[2] == "charts":
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    continue
                
                is_executable = os.access(file_path, os.X_OK)
                
                files_to_create.append({
                    'path': str(rel_path),
                    'content': content,
                    'executable': is_executable
                })
        
        return files_to_create
    
    @staticmethod
    def _generate_mkdir_section(files: List[Dict[str, Any]]) -> str:
        """Generate mkdir commands for directories"""
        dirs_to_create = set()
        for f in files:
            parent = str(Path(f['path']).parent)
            if parent and parent != '.':
                dirs_to_create.add(parent)
        
        return "\n".join(f'mkdir -p "{d}"' for d in sorted(dirs_to_create))
    
    @staticmethod
    def _generate_files_section(files: List[Dict[str, Any]]) -> str:
        """Generate heredoc file creation section"""
        sections = []
        
        for f in files:
            content = f['content']
            eof_marker = "FILEEOF"
            while eof_marker in content:
                eof_marker = f"EOF{hash(content) % 10000}"
            
            section = f'''
cat << '{eof_marker}' > "{f['path']}"
{content}
{eof_marker}
'''
            if f['executable']:
                section += f'chmod +x "{f["path"]}"\n'
            
            sections.append(section)
        
        return "".join(sections)
    
    @staticmethod
    def _generate_helm_section(helm_charts: List[Dict[str, str]]) -> str:
        """Generate helm repo and pull section"""
        if not helm_charts:
            return ""
        
        lines = []
        repos_added = set()
        
        for chart in helm_charts:
            chart_repo = chart.get('repository', '')
            if not chart_repo:
                continue
            
            chart_id = chart.get('id', chart['name'])
            chart_name = chart['name']
            chart_version = chart['version']
            category = chart.get('category', 'apps')
            dest_dir = f"charts/{category}/{chart_id}/charts"
            
            is_oci = chart_repo.startswith("oci://")
            
            if is_oci:
                # Check if OCI repo already ends with chart name
                if chart_repo.endswith(f"/{chart_name}"):
                    oci_url = chart_repo
                else:
                    oci_url = f"{chart_repo}/{chart_name}"
                lines.append(f'''rm -rf "{dest_dir}/{chart_name}" 2>/dev/null || true
mkdir -p "{dest_dir}"
helm pull {oci_url} --version {chart_version} --untar --untardir "{dest_dir}"
''')
            else:
                repo_name = chart_repo.replace("https://", "").replace("http://", "").replace("/", "-").replace(".", "-")[:30]
                
                if chart_repo not in repos_added:
                    lines.append(f'helm repo add {repo_name} {chart_repo} 2>/dev/null || true\n')
                    repos_added.add(chart_repo)
                
                lines.append(f'''rm -rf "{dest_dir}/{chart_name}" 2>/dev/null || true
mkdir -p "{dest_dir}"
helm pull {repo_name}/{chart_name} --version {chart_version} --untar --untardir "{dest_dir}"
''')
        
        return f'''
info "Downloading Helm charts from upstream..."
helm repo update 2>/dev/null || true
{"".join(lines)}
success "Helm charts downloaded"
'''
    
    @staticmethod
    def _render_script(
        cluster_name: str,
        repo_url: str,
        branch: str,
        mkdir_section: str,
        files_section: str,
        helm_section: str
    ) -> str:
        """Render the final bootstrap script"""
        return f'''#!/usr/bin/env bash
#
# K8s Bootstrap Installer
# Cluster: {cluster_name}
# Repository: {repo_url}
#
# Usage:
#   bash -c "$(curl -fsSL <url>)"
#   bash -c "$(curl -fsSL <url>)" -- -k /path/to/kubeconfig
#

set -euo pipefail

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
NC='\\033[0m'

info() {{ echo -e "${{BLUE}}ℹ${{NC}} $1"; }}
success() {{ echo -e "${{GREEN}}✓${{NC}} $1"; }}
warn() {{ echo -e "${{YELLOW}}⚠${{NC}} $1"; }}
error() {{ echo -e "${{RED}}✗${{NC}} $1" >&2; }}

# Configuration
CLUSTER_NAME="{cluster_name}"
REPO_URL="{repo_url}"
BRANCH="{branch}"

# Arguments
KUBECONFIG_ARG=""
CONTEXT_ARG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--kubeconfig) KUBECONFIG_ARG="$2"; shift 2 ;;
        -c|--context) CONTEXT_ARG="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -k, --kubeconfig PATH   Custom kubeconfig"
            echo "  -c, --context NAME      Kubernetes context"
            echo "  -h, --help              Show help"
            exit 0
            ;;
        --) shift; break ;;
        *) break ;;
    esac
done

# Helpers for kubectl/helm with custom kubeconfig
kctl() {{
    local args=()
    [[ -n "$KUBECONFIG_ARG" ]] && args+=(--kubeconfig "$KUBECONFIG_ARG")
    [[ -n "$CONTEXT_ARG" ]] && args+=(--context "$CONTEXT_ARG")
    kubectl "${{args[@]}}" "$@"
}}

hlm() {{
    local args=()
    [[ -n "$KUBECONFIG_ARG" ]] && args+=(--kubeconfig "$KUBECONFIG_ARG")
    [[ -n "$CONTEXT_ARG" ]] && args+=(--kube-context "$CONTEXT_ARG")
    helm "${{args[@]}}" "$@"
}}

# Main
echo ""
echo -e "${{CYAN}}╔══════════════════════════════════════════════════════════════╗${{NC}}"
echo -e "${{CYAN}}║       K8s Bootstrap - {cluster_name:<36} ║${{NC}}"
echo -e "${{CYAN}}╚══════════════════════════════════════════════════════════════╝${{NC}}"
echo ""

# Check tools
for cmd in kubectl helm git; do
    command -v $cmd &>/dev/null || {{ error "$cmd not installed"; exit 1; }}
done
success "Required tools installed"

# Check cluster
if ! kctl cluster-info &>/dev/null; then
    error "Cannot connect to Kubernetes cluster"
    exit 1
fi
success "Connected to cluster"

# Setup directory
TARGET_DIR="./$CLUSTER_NAME"

if [[ -d "$TARGET_DIR" ]]; then
    error "Directory already exists: $TARGET_DIR"
    error "For updates, use the Update mode in the UI"
    exit 1
fi

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"
info "Working in: $(pwd)"

# Create directories
info "Creating directories..."
{mkdir_section}

# Create files
info "Creating files..."
{files_section}
success "Files created"

# Download Helm charts
{helm_section}

# Run bootstrap
chmod +x bootstrap.sh

info "Starting bootstrap..."
BOOTSTRAP_ARGS=()
[[ -n "$KUBECONFIG_ARG" ]] && BOOTSTRAP_ARGS+=(-k "$KUBECONFIG_ARG")
[[ -n "$CONTEXT_ARG" ]] && BOOTSTRAP_ARGS+=(-c "$CONTEXT_ARG")

exec ./bootstrap.sh "${{BOOTSTRAP_ARGS[@]}}"
'''
