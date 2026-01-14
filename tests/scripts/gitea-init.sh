#!/bin/sh
# Initialize Gitea with test user, access tokens, and repos (public + private)
# This script is executed inside the gitea-init container

set -e

echo "Waiting for Gitea to be fully ready..."
sleep 5

GITEA_URL="http://gitea:3000"
USERNAME="test"
PASSWORD="test1234"
EMAIL="test@test.local"

# Register test user via API (Gitea allows registration by default)
echo "📝 Creating test user via registration..."
curl -sf -X POST "$GITEA_URL/user/sign_up" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "user_name=$USERNAME&email=$EMAIL&password=$PASSWORD&retype=$PASSWORD" \
  -o /dev/null || echo "User might already exist"

# Verify user exists
if ! curl -sf -u "$USERNAME:$PASSWORD" "$GITEA_URL/api/v1/user" -o /dev/null; then
  echo "❌ Could not verify user - trying admin API..."
  curl -sf -X POST "$GITEA_URL/api/v1/admin/users" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"must_change_password\":false}" \
    -o /dev/null || true
fi

echo "✅ Test user ready"

# Create access token for API authentication
echo "🔑 Creating access token..."
TOKEN_RESPONSE=$(curl -sf -X POST "$GITEA_URL/api/v1/users/$USERNAME/tokens" \
  -u "$USERNAME:$PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"name":"test-token","scopes":["write:repository","write:user"]}' 2>/dev/null || echo "{}")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"sha1":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "⚠️ Could not create new token, might already exist. Trying to delete and recreate..."
  curl -sf -X DELETE "$GITEA_URL/api/v1/users/$USERNAME/tokens/test-token" \
    -u "$USERNAME:$PASSWORD" -o /dev/null || true
  
  TOKEN_RESPONSE=$(curl -sf -X POST "$GITEA_URL/api/v1/users/$USERNAME/tokens" \
    -u "$USERNAME:$PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{"name":"test-token","scopes":["write:repository","write:user"]}' 2>/dev/null || echo "{}")
  ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"sha1":"[^"]*"' | cut -d'"' -f4)
fi

if [ -n "$ACCESS_TOKEN" ]; then
  echo "✅ Access token created: $(echo "$ACCESS_TOKEN" | cut -c1-8)..."
  # Save token to a file that can be read by tests
  echo "$ACCESS_TOKEN" > /tmp/gitea-token.txt
else
  echo "⚠️ Could not create access token"
fi

# Create public repository
echo "📦 Creating public repository..."
curl -sf -X POST "$GITEA_URL/api/v1/user/repos" \
  -u "$USERNAME:$PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"name":"public-repo","private":false,"auto_init":true,"description":"Public test repository"}' \
  -o /dev/null && echo "✅ Public repo created" || echo "⚠️ Public repo might already exist"

# Create private repository
echo "🔒 Creating private repository..."
curl -sf -X POST "$GITEA_URL/api/v1/user/repos" \
  -u "$USERNAME:$PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"name":"private-repo","private":true,"auto_init":true,"description":"Private test repository"}' \
  -o /dev/null && echo "✅ Private repo created" || echo "⚠️ Private repo might already exist"

# Verify repos
echo "🔍 Verifying repositories..."
curl -sf -u "$USERNAME:$PASSWORD" "$GITEA_URL/api/v1/repos/$USERNAME/public-repo" -o /dev/null && echo "  ✓ public-repo accessible"
curl -sf -u "$USERNAME:$PASSWORD" "$GITEA_URL/api/v1/repos/$USERNAME/private-repo" -o /dev/null && echo "  ✓ private-repo accessible"

# Test that private repo requires auth
if curl -sf "$GITEA_URL/api/v1/repos/$USERNAME/private-repo" -o /dev/null 2>/dev/null; then
  echo "  ⚠️ private-repo is accessible without auth (unexpected)"
else
  echo "  ✓ private-repo requires authentication"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "Gitea setup complete!"
echo "  URL: $GITEA_URL"
echo "  User: $USERNAME"
echo "  Public repo: $GITEA_URL/$USERNAME/public-repo.git"
echo "  Private repo: $GITEA_URL/$USERNAME/private-repo.git"
echo "════════════════════════════════════════════════════════════"
