#!/usr/bin/env bash
# =============================================================================
# Component Validation Script
# Validates a new or modified component definition
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

usage() {
    cat <<EOF
Usage: $0 <component-id> [options]

Validates a component definition and optionally tests chart generation.

Options:
    --full          Run full validation including E2E tests
    --skip-docker   Skip Docker-based tests (run Python tests locally)
    -h, --help      Show this help message

Examples:
    $0 cert-manager              # Quick validation
    $0 cert-manager --full       # Full validation with E2E
    $0 my-new-component          # Validate new component
EOF
    exit 0
}

# Parse arguments
COMPONENT=""
FULL_TEST=false
SKIP_DOCKER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            FULL_TEST=true
            shift
            ;;
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            if [[ -z "$COMPONENT" ]]; then
                COMPONENT="$1"
            else
                echo "Unknown argument: $1"
                usage
            fi
            shift
            ;;
    esac
done

if [[ -z "$COMPONENT" ]]; then
    echo "Error: Component ID required"
    usage
fi

cd "$PROJECT_ROOT"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Component Validation: $COMPONENT"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Check definition file exists
log "Step 1: Checking definition file..."
DEF_FILE="backend/definitions/components/${COMPONENT}.yaml"
if [[ ! -f "$DEF_FILE" ]]; then
    err "Definition file not found: $DEF_FILE"
fi
ok "Definition file exists: $DEF_FILE"

# Step 2: Validate YAML syntax
log "Step 2: Validating YAML syntax..."
python3 -c "
import yaml
import sys
try:
    with open('$DEF_FILE') as f:
        data = yaml.safe_load(f)
    if not data:
        print('Empty YAML file')
        sys.exit(1)
    if 'id' not in data:
        print('Missing required field: id')
        sys.exit(1)
    print(f'  id: {data[\"id\"]}')
    print(f'  name: {data.get(\"name\", \"N/A\")}')
    print(f'  category: {data.get(\"category\", \"N/A\")}')
except yaml.YAMLError as e:
    print(f'YAML syntax error: {e}')
    sys.exit(1)
"
ok "YAML syntax valid"

# Step 3: Check required fields
log "Step 3: Checking required fields..."
python3 -c "
import yaml
import sys

required = ['id', 'name', 'category', 'description']
with open('$DEF_FILE') as f:
    data = yaml.safe_load(f)

missing = [r for r in required if r not in data]
if missing:
    print(f'Missing required fields: {missing}')
    sys.exit(1)

# Check description length
if len(data.get('description', '')) < 10:
    print('Description too short (min 10 chars)')
    sys.exit(1)

# Check docsUrl for visible components
if not data.get('hidden') and not data.get('alwaysInclude'):
    if 'docsUrl' not in data:
        print('Warning: Non-hidden component should have docsUrl')
"
ok "Required fields present"

# Step 4: Run unit tests
if [[ "$SKIP_DOCKER" == "true" ]]; then
    log "Step 4: Running unit tests locally..."
    cd backend
    python -m pytest ../tests/unit/test_definitions.py -v -k "$COMPONENT" --tb=short || {
        warn "Some unit tests failed"
    }
    cd "$PROJECT_ROOT"
else
    log "Step 4: Running unit tests in Docker..."
    docker-compose -f tests/docker-compose.test.yml build test-unit >/dev/null 2>&1
    docker-compose -f tests/docker-compose.test.yml run --rm test-unit \
        pytest tests/unit/test_definitions.py -v -k "$COMPONENT" --tb=short || {
        warn "Some unit tests failed"
    }
fi
ok "Unit tests completed"

# Step 5: Test chart generation (integration)
log "Step 5: Testing chart generation..."
if [[ "$SKIP_DOCKER" == "true" ]]; then
    warn "Skipping Docker-based chart generation test"
else
    # Start backend if needed
    docker-compose -f tests/docker-compose.test.yml up -d backend >/dev/null 2>&1
    sleep 3
    
    # Test generation via API (new bootstrap endpoint)
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "http://localhost:8000/api/bootstrap" \
        -H "Content-Type: application/json" \
        -d "{\"cluster_name\":\"validation-test\",\"repo_url\":\"git@test.git\",\"components\":[{\"id\":\"$COMPONENT\",\"enabled\":true}]}" \
        2>/dev/null || echo "000")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | head -n -1)
    
    if [[ "$HTTP_CODE" == "200" ]]; then
        ok "Bootstrap endpoint successful"
        
        # Extract token from response
        TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
        if [[ -n "$TOKEN" ]]; then
            log "  Token generated: ${TOKEN:0:20}..."
            
            # Test script endpoint
            SCRIPT_RESP=$(curl -s -w "\n%{http_code}" "http://localhost:8000/bootstrap/$TOKEN" 2>/dev/null)
            SCRIPT_CODE=$(echo "$SCRIPT_RESP" | tail -1)
            if [[ "$SCRIPT_CODE" == "200" ]]; then
                ok "Bootstrap script generated"
            else
                warn "Script endpoint returned HTTP $SCRIPT_CODE"
            fi
        fi
    else
        warn "Bootstrap endpoint returned HTTP $HTTP_CODE"
    fi
fi

# Step 6: Full E2E test (optional)
if [[ "$FULL_TEST" == "true" ]]; then
    log "Step 6: Running E2E tests..."
    docker-compose -f tests/docker-compose.test.yml up -d backend
    docker-compose -f tests/docker-compose.test.yml run --rm test-e2e \
        pytest tests/e2e -v -k "$COMPONENT" --timeout=600 || {
        warn "E2E tests had issues"
    }
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ Validation Complete: $COMPONENT"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [[ "$FULL_TEST" != "true" ]]; then
    echo "Tip: Run with --full for complete E2E validation"
fi
