#!/bin/bash
# Initialize Gitea with test user
# This script is run inside the gitea-init container

set -e

GITEA_URL="${GITEA_URL:-http://gitea:3000}"
MAX_RETRIES=30
RETRY_DELAY=2

echo "⏳ Waiting for Gitea to be ready..."

for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "$GITEA_URL/api/v1/version" > /dev/null 2>&1; then
        echo "✅ Gitea is ready"
        break
    fi
    
    if [ $i -eq $MAX_RETRIES ]; then
        echo "❌ Gitea did not become ready in time"
        exit 1
    fi
    
    echo "   Attempt $i/$MAX_RETRIES..."
    sleep $RETRY_DELAY
done

# Try to create user using Gitea CLI (if available inside gitea container)
# Otherwise use API (requires admin setup)
echo "📝 Creating test user..."

# Check if user already exists
USER_EXISTS=$(curl -sf "$GITEA_URL/api/v1/users/test" -o /dev/null && echo "yes" || echo "no")

if [ "$USER_EXISTS" = "yes" ]; then
    echo "✅ Test user already exists"
    exit 0
fi

# Create user via Gitea admin API (if admin token is available)
# For testing, we use the built-in admin features
# This requires the admin user to be created first during Gitea setup

# Alternative: Create user using gitea CLI inside the container
# We'll do this via docker exec from the test container

echo "⚠️  User creation may need to be done via Gitea web UI or CLI"
echo "   Navigate to: $GITEA_URL"
echo "   Or run: docker exec gitea gitea admin user create --username test --password test1234 --email test@test.local --admin"

exit 0
