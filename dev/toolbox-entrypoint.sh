#!/bin/bash
#
# Toolbox Entrypoint - Sets up kind cluster and tools
#
set -e

CLUSTER_NAME="${CLUSTER_NAME:-k8s-bootstrap-dev}"
KUBECONFIG="${KUBECONFIG:-/workspace/.kube/config}"

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

# Configure git defaults
configure_git() {
    git config --global user.email "${GITEA_EMAIL:-dev@localhost}"
    git config --global user.name "${GITEA_USER:-dev}"
    git config --global init.defaultBranch main
    success "Git configured (${GITEA_USER:-dev} <${GITEA_EMAIL:-dev@localhost}>)"
}

# Wait for Docker to be available
wait_for_docker() {
    info "Waiting for Docker..."
    for i in {1..30}; do
        if docker info &>/dev/null; then
            success "Docker is available"
            return 0
        fi
        sleep 1
    done
    echo "Docker not available"
    exit 1
}

# Fix kubeconfig for Docker network access
fix_kubeconfig() {
    # Get the control plane container IP
    local container_name="${CLUSTER_NAME}-control-plane"
    local container_ip
    container_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container_name" 2>/dev/null || true)
    
    if [[ -n "$container_ip" ]] && [[ -f "$KUBECONFIG" ]]; then
        # Replace localhost/127.0.0.1 with container IP
        sed -i "s|https://127\.0\.0\.1:[0-9]*|https://${container_ip}:6443|g" "$KUBECONFIG"
        sed -i "s|https://localhost:[0-9]*|https://${container_ip}:6443|g" "$KUBECONFIG"
        info "Fixed kubeconfig to use ${container_ip}:6443"
    fi
}

# Create kind cluster
create_cluster() {
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        success "Cluster '${CLUSTER_NAME}' already exists"
        kind export kubeconfig --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG"
        fix_kubeconfig
    else
        info "Creating kind cluster '${CLUSTER_NAME}'..."
        
        cat > /tmp/kind-config.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ${CLUSTER_NAME}
networking:
  podSubnet: "10.244.0.0/16"
  serviceSubnet: "10.96.0.0/12"
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 8080
        protocol: TCP
      - containerPort: 443
        hostPort: 8443
        protocol: TCP
  - role: worker
EOF
        
        kind create cluster \
            --name "$CLUSTER_NAME" \
            --config /tmp/kind-config.yaml \
            --kubeconfig "$KUBECONFIG" \
            --wait 120s
        
        fix_kubeconfig
        success "Cluster created"
    fi
    
    # Make kubeconfig accessible
    chmod 644 "$KUBECONFIG" 2>/dev/null || true
}

# Print status
show_status() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         K8s Bootstrap - Developer Toolbox                    ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    echo -e "${BLUE}Kubernetes:${NC}"
    kubectl get nodes 2>/dev/null || echo "  Cluster not ready yet"
    echo ""
    
    echo -e "${BLUE}Services:${NC}"
    echo "  Frontend: http://localhost:3000"
    echo "  Backend:  http://localhost:8000"
    echo "  Gitea:    http://localhost:3030 (dev/dev12345)"
    echo ""
    
    echo -e "${BLUE}Quick Commands:${NC}"
    echo "  kubectl get nodes              # Check cluster"
    echo "  kubectl get pods -A            # All pods"
    echo "  ./run-bootstrap.sh             # Run bootstrap script"
    echo ""
    
    echo -e "${BLUE}Workflow:${NC}"
    echo "  1. Open http://localhost:3000"
    echo "  2. Select components"
    echo "  3. Set repo: http://gitea:3000/dev/bootstrap-test.git"
    echo "  4. Copy curl command"
    echo "  5. Run here: bash -c \"\$(curl -fsSL ...)\""
    echo ""
}

# Main
case "${1:-}" in
    init)
        configure_git
        wait_for_docker
        create_cluster
        show_status
        ;;
    cluster)
        configure_git
        wait_for_docker
        create_cluster
        ;;
    status)
        show_status
        ;;
    delete-cluster)
        kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
        rm -f "$KUBECONFIG"
        success "Cluster deleted"
        ;;
    bash|sh)
        exec bash
        ;;
    *)
        # Default: init and start shell
        if [[ -z "${1:-}" ]] || [[ "$1" == "bash" ]]; then
            configure_git
            wait_for_docker
            create_cluster
            show_status
            exec bash
        else
            exec "$@"
        fi
        ;;
esac
