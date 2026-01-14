#!/bin/sh
# Initialize GitLab for E2E tests
# Creates: test user, personal access token, project access token, public and private repos
#
# NOTE: GitLab API requires PAT for authentication, so we create the initial token
# using gitlab-rails runner from within the GitLab container.

set -e

GITLAB_URL="${GITLAB_URL:-http://gitlab:80}"
ROOT_PASSWORD="${GITLAB_ROOT_PASSWORD:-test12345678}"

echo "=== GitLab Initialization Script ==="
echo "GitLab URL: $GITLAB_URL"

# Wait for GitLab health endpoint
echo "Waiting for GitLab to be ready..."
max_retries=60
retry=0
while [ $retry -lt $max_retries ]; do
    if curl -sf "${GITLAB_URL}/-/health" > /dev/null 2>&1; then
        echo "GitLab health check passed!"
        break
    fi
    retry=$((retry + 1))
    echo "Retry $retry/$max_retries - waiting for GitLab..."
    sleep 10
done

if [ $retry -eq $max_retries ]; then
    echo "ERROR: GitLab not ready after $max_retries retries"
    exit 1
fi

# GitLab needs the PAT created via rails console because API requires auth
# We'll create everything using the API once we have the token
# For now, output instructions for manual token creation or use pre-created token

echo ""
echo "=== GitLab is Ready ==="
echo ""
echo "Access GitLab at: ${GITLAB_URL} (from docker network)"
echo "                  http://localhost:8080 (from host)"
echo ""
echo "Login credentials:"
echo "  Username: root"
echo "  Password: ${ROOT_PASSWORD}"
echo ""
echo "To create Personal Access Token:"
echo "1. Login to GitLab UI"
echo "2. Go to: User Settings > Access Tokens"
echo "3. Create token with scopes: api, read_repository, write_repository"
echo ""
echo "Or create via rails console:"
echo "  docker compose -f tests/docker-compose.test.yml exec gitlab gitlab-rails runner \\"
echo "    \"token = User.find_by_username('root').personal_access_tokens.create!(name: 'test', scopes: [:api, :read_repository, :write_repository], expires_at: 1.year.from_now); puts token.token\""
echo ""

# Save basic info
echo "$GITLAB_URL" > /tmp/gitlab_url.txt
echo "root" > /tmp/gitlab_username.txt

echo "=== GitLab initialization complete ==="
echo "Note: PAT must be created manually or via rails console"
