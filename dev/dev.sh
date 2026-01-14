#!/usr/bin/env bash
#
# K8s Bootstrap - Developer Environment
# =====================================
#
# Requirements: Docker only!
#
# Usage:
#   ./dev.sh start    - Start environment (services + k8s in container)
#   ./dev.sh shell    - Open shell with kubectl, helm, git (in container)
#   ./dev.sh stop     - Stop environment
#   ./dev.sh clean    - Remove everything
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1" >&2; }

# Check Docker
check_docker() {
    if ! command -v docker &>/dev/null; then
        error "Docker is required. Install: https://docs.docker.com/get-docker/"
        exit 1
    fi
    if ! docker info &>/dev/null; then
        error "Docker daemon is not running"
        exit 1
    fi
}

# Ensure workspace directory exists
ensure_workspace() {
    mkdir -p "${SCRIPT_DIR}/workspace/.kube"
    mkdir -p "${SCRIPT_DIR}/workspace/repos"
}

# Start services
start() {
    info "Starting K8s Bootstrap Dev Environment..."
    ensure_workspace
    
    cd "$SCRIPT_DIR"
    
    # Start web services first
    docker compose up -d gitea backend frontend gitea-init
    
    info "Waiting for services..."
    sleep 5
    
    # Create kind cluster via toolbox (runs in background, creates cluster, exits)
    info "Creating Kubernetes cluster..."
    docker compose run --rm toolbox cluster
    
    success "Environment ready!"
    echo ""
    echo -e "${CYAN}URLs:${NC}"
    echo "  Frontend: http://localhost:3000"
    echo "  Backend:  http://localhost:8000"
    echo "  Gitea:    http://localhost:3030 (dev/dev12345)"
    echo ""
    echo -e "${CYAN}Kubernetes:${NC}"
    echo "  KUBECONFIG: ${SCRIPT_DIR}/workspace/.kube/config"
    echo "  kubectl get nodes"
    echo ""
    echo -e "${CYAN}Next:${NC}"
    echo "  Run 'make dev-shell' to open toolbox with kubectl, helm, etc."
    echo ""
}

# Open shell in toolbox
shell() {
    info "Opening toolbox shell (with kind cluster, kubectl, helm, git)..."
    ensure_workspace
    
    cd "$SCRIPT_DIR"
    
    # Start services if not running
    if ! docker compose ps --status running 2>/dev/null | grep -q backend; then
        info "Starting services first..."
        docker compose up -d gitea backend frontend gitea-init
        sleep 5
    fi
    
    # Remove old toolbox shell if exists
    docker rm -f k8s-bootstrap-toolbox-shell 2>/dev/null || true
    
    # Run toolbox interactively with fixed name
    docker compose run --rm --name k8s-bootstrap-toolbox-shell toolbox
}

# Show status
status() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         K8s Bootstrap - Developer Environment                ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    echo -e "${BLUE}Services:${NC}"
    cd "$SCRIPT_DIR"
    docker compose ps 2>/dev/null || echo "  Not running"
    echo ""
    
    echo -e "${BLUE}URLs:${NC}"
    echo "  Frontend: http://localhost:3000"
    echo "  Backend:  http://localhost:8000"
    echo "  Gitea:    http://localhost:3030 (dev/dev12345)"
    echo ""
    
    echo -e "${BLUE}Workspace:${NC}"
    echo "  ${SCRIPT_DIR}/workspace/"
    echo ""
    
    echo -e "${BLUE}Commands:${NC}"
    echo "  make dev         - Start environment"
    echo "  make dev-shell   - Open toolbox shell"
    echo "  make dev-stop    - Stop environment"
    echo "  make dev-clean   - Remove everything"
    echo ""
}

# Stop services
stop() {
    info "Stopping environment..."
    cd "$SCRIPT_DIR"
    
    # Delete kind cluster first (to free the network)
    info "Deleting Kubernetes cluster..."
    docker rm -f k8s-bootstrap-dev-control-plane k8s-bootstrap-dev-worker 2>/dev/null || true
    
    # Stop services
    info "Stopping services..."
    docker compose down
    
    success "Stopped"
}

# Clean everything
clean() {
    local force=false
    if [[ "${1:-}" == "-f" || "${1:-}" == "--force" ]]; then
        force=true
    fi
    
    if [[ "$force" != "true" ]]; then
        warn "This will remove all data including the workspace. Continue? [y/N]"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            info "Cancelled"
            exit 0
        fi
    fi
    
    info "Stopping and removing..."
    cd "$SCRIPT_DIR"
    
    # Remove kind cluster first (it uses docker socket, so must be deleted directly)
    # Try via toolbox container first, then directly
    docker exec k8s-bootstrap-toolbox kind delete cluster --name k8s-bootstrap-dev 2>/dev/null || \
        kind delete cluster --name k8s-bootstrap-dev 2>/dev/null || \
        docker rm -f k8s-bootstrap-dev-control-plane k8s-bootstrap-dev-worker 2>/dev/null || true
    
    # Stop docker compose
    docker compose down -v --remove-orphans 2>/dev/null || true
    
    # Remove named volumes explicitly
    docker volume rm k8s-bootstrap-gitea-data k8s-bootstrap-gitea-config 2>/dev/null || true
    
    # Prune unused volumes (dangling anonymous volumes from kind etc)
    docker volume prune -f 2>/dev/null || true
    
    # Clean workspace (keep directory structure)
    rm -rf "${SCRIPT_DIR}/workspace/.kube"/* 2>/dev/null || true
    rm -rf "${SCRIPT_DIR}/workspace/repos"/* 2>/dev/null || true
    
    success "Cleaned"
}

# Show logs
logs() {
    cd "$SCRIPT_DIR"
    docker compose logs -f "$@"
}

# Usage
usage() {
    echo "K8s Bootstrap - Developer Environment"
    echo ""
    echo "Requirements: Docker only!"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  start     Start services (Gitea, Backend, Frontend)"
    echo "  shell     Open toolbox shell with kubectl, helm, git, kind cluster"
    echo "  stop      Stop services"
    echo "  clean     Remove everything including data"
    echo "  status    Show status"
    echo "  logs      Show logs"
    echo ""
    echo "Workflow:"
    echo "  1. $0 start         # Start services + k8s cluster"
    echo "  2. $0 shell         # Open toolbox shell"
    echo "  3. Open http://localhost:3000, select components"
    echo "  4. Run curl command in the shell"
    echo "  5. Watch: kubectl get kustomizations,helmreleases -A -w"
    echo ""
}

# Main
check_docker

case "${1:-}" in
    start)
        start
        ;;
    shell)
        shell
        ;;
    stop)
        stop
        ;;
    clean)
        shift
        clean "$@"
        ;;
    status)
        status
        ;;
    logs)
        shift
        logs "$@"
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage
        exit 1
        ;;
esac
