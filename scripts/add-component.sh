#!/usr/bin/env bash
#
# Add Component - Always runs in Docker
# =====================================
#
# No local dependencies needed - everything runs in a container.
#
# Usage:
#   ./scripts/add-component.sh                    # Interactive mode
#   ./scripts/add-component.sh --list-categories  # Show categories
#   ./scripts/add-component.sh --id external-dns --repo https://... --chart external-dns
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

IMAGE_NAME="k8s-bootstrap-generator"

# Check Docker
if ! command -v docker &>/dev/null; then
    echo -e "❌ Docker is required. Install: https://docs.docker.com/get-docker/"
    exit 1
fi

# Build image if needed
build_image() {
    if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
        echo -e "${BLUE}ℹ${NC} Building generator image (first run only)..."
        docker build -q -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile.generator" "$SCRIPT_DIR"
        echo -e "${GREEN}✓${NC} Image built"
    fi
}

# Run generator
run_generator() {
    build_image
    
    # Determine if we need interactive mode
    DOCKER_FLAGS="--rm"
    if [ -t 0 ] && [ $# -eq 0 ]; then
        # Interactive mode - need TTY
        DOCKER_FLAGS="--rm -it"
    fi
    
    docker run $DOCKER_FLAGS \
        -v "$PROJECT_ROOT:/app" \
        -w /app \
        "$IMAGE_NAME" \
        "$@"
}

run_generator "$@"
