# Production Deployment

How to deploy K8s Bootstrap for production use with Docker Compose, TLS, and a reverse proxy.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Deploy](#quick-deploy)
- [Configuration](#configuration)
- [Reverse Proxy (nginx-proxy)](#reverse-proxy-nginx-proxy)
- [Reverse Proxy (Traefik)](#reverse-proxy-traefik)
- [Gitea as Remote Git Server](#gitea-as-remote-git-server)
- [Security Considerations](#security-considerations)
- [Backup and Restore](#backup-and-restore)
- [Upgrading](#upgrading)
- [Monitoring](#monitoring)

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- A domain name pointing to your server (e.g. `k8s-bootstrap.example.com`)
- Ports 80 and 443 open (for TLS via Let's Encrypt)
- (Optional) A running Git server reachable from your users' clusters

## Quick Deploy

```bash
# 1. Clone the repository
git clone https://github.com/your-org/k8s-bootstrap.git
cd k8s-bootstrap

# 2. Create .env from the template
cp .env.example .env

# 3. Edit .env — set DOMAIN, GITHUB_REPOSITORY, VERSION
vi .env

# 4. Create the external Docker network for the reverse proxy
docker network create nginx-proxy

# 5. Start the reverse proxy (see section below)
# ...

# 6. Start K8s Bootstrap
docker compose -f docker-compose.prod.yml up -d

# 7. Verify
curl -s https://k8s-bootstrap.example.com/api/health
```

## Configuration

All configuration is done through environment variables in `.env`. See [`.env.example`](../.env.example) for the full list.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DOMAIN` | Public domain | `k8s-bootstrap.example.com` |
| `GITHUB_REPOSITORY` | GHCR image path | `your-org/k8s-bootstrap` |
| `VERSION` | Image tag | `v1.0.0` or `latest` |

### Backend Variables

All backend variables use the `K8S_BOOTSTRAP_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_BOOTSTRAP_DEBUG` | `false` | Enable debug logging |
| `K8S_BOOTSTRAP_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON array) |
| `K8S_BOOTSTRAP_STORAGE_DIR` | `/tmp/k8s-bootstrap-sessions` | Session file storage path |
| `K8S_BOOTSTRAP_TOKEN_TTL_MINUTES` | `60` | Bootstrap token expiration |
| `K8S_BOOTSTRAP_SESSION_TTL_MINUTES` | `60` | Session expiration |

### Production Overrides

For production, at minimum set:

```bash
DOMAIN=k8s-bootstrap.example.com
K8S_BOOTSTRAP_DEBUG=false
K8S_BOOTSTRAP_CORS_ORIGINS=["https://k8s-bootstrap.example.com"]
```

## Reverse Proxy (nginx-proxy)

The production compose file expects an external `nginx-proxy` Docker network. The recommended setup uses [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) with automatic Let's Encrypt certificates.

### Start nginx-proxy

```bash
docker compose -f docker-compose.nginx-proxy.yml up -d
```

Or run manually:

```bash
docker run -d \
  --name nginx-proxy \
  --network nginx-proxy \
  -p 80:80 -p 443:443 \
  -v /var/run/docker.sock:/tmp/docker.sock:ro \
  -v certs:/etc/nginx/certs \
  -v vhost:/etc/nginx/vhost.d \
  -v html:/usr/share/nginx/html \
  nginxproxy/nginx-proxy:latest

docker run -d \
  --name acme-companion \
  --network nginx-proxy \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v certs:/etc/nginx/certs \
  -v vhost:/etc/nginx/vhost.d \
  -v html:/usr/share/nginx/html \
  -v acme:/etc/acme.sh \
  --env DEFAULT_EMAIL=admin@example.com \
  nginxproxy/acme-companion:latest
```

The K8s Bootstrap frontend container exposes `VIRTUAL_HOST` and `LETSENCRYPT_HOST` environment variables (set from `DOMAIN` in `.env`), which nginx-proxy picks up automatically.

## Reverse Proxy (Traefik)

If you prefer Traefik, add labels to the frontend service in a `docker-compose.override.yml`:

```yaml
services:
  frontend:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.k8s-bootstrap.rule=Host(`k8s-bootstrap.example.com`)"
      - "traefik.http.routers.k8s-bootstrap.entrypoints=websecure"
      - "traefik.http.routers.k8s-bootstrap.tls.certresolver=letsencrypt"
      - "traefik.http.services.k8s-bootstrap.loadbalancer.server.port=3000"
    networks:
      - traefik
      - internal

networks:
  traefik:
    external: true
```

## Gitea as Remote Git Server

K8s Bootstrap pushes generated repositories to a Git remote. In air-gapped or local setups, [Gitea](https://gitea.io) works well:

```bash
docker run -d \
  --name gitea \
  -p 3030:3000 -p 2222:22 \
  -v gitea-data:/data \
  gitea/gitea:latest
```

Configure in the K8s Bootstrap UI:
- **Repository URL:** `http://gitea:3000/org/repo.git` (container URL) or `http://your-server:3030/org/repo.git` (host URL)
- **Branch:** `main`

For SSH access, add an SSH key in Gitea and use `ssh://git@gitea:22/org/repo.git`.

## Security Considerations

### Network Isolation

The production compose file uses two networks:

- `nginx-proxy` (external) — connects the frontend to the reverse proxy
- `internal` (bridge) — connects frontend to backend; the backend is not exposed externally

### Token Security

- Bootstrap tokens are one-time use by default
- Tokens expire after `K8S_BOOTSTRAP_TOKEN_TTL_MINUTES` (default: 60 minutes)
- Session files are cleaned up automatically
- Never share bootstrap URLs in public channels — they contain the generated scripts

### TLS

- Always deploy behind a TLS-terminating reverse proxy in production
- Set `K8S_BOOTSTRAP_CORS_ORIGINS` to your HTTPS domain only

### Container Security

- Backend runs as a non-root user inside the container
- No host volumes are mounted in production (except `backend_data` for sessions)
- Use specific image tags (`VERSION=v1.0.0`), not `latest`, in production

### Access Control

K8s Bootstrap does not include authentication. If you need to restrict access:

- Use HTTP basic auth at the reverse proxy level
- Use an OAuth2 proxy (e.g., [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy)) in front of the service
- Restrict network access with firewall rules

## Backup and Restore

### What to Back Up

| Item | Location | Method |
|------|----------|--------|
| Generated sessions | `backend_data` volume | `docker volume` backup |
| Configuration | `.env` | File backup |

Sessions are ephemeral (1 hour TTL), so the critical item is your `.env` file and any custom compose overrides.

### Volume Backup

```bash
# Backup
docker run --rm \
  -v k8s-bootstrap_backend_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/backend-data.tar.gz -C /data .

# Restore
docker run --rm \
  -v k8s-bootstrap_backend_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/backend-data.tar.gz -C /data
```

## Upgrading

```bash
# 1. Pull new images
VERSION=v1.1.0
sed -i "s/^VERSION=.*/VERSION=${VERSION}/" .env

# 2. Recreate containers
docker compose -f docker-compose.prod.yml up -d

# 3. Verify
curl -s https://k8s-bootstrap.example.com/api/health
```

Rolling back: change `VERSION` in `.env` to the previous tag and run `docker compose up -d` again.

## Monitoring

### Health Check

The backend exposes a health endpoint:

```bash
curl http://localhost:8000/api/health
```

Both frontend and backend containers have Docker health checks configured in the compose file.

### Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Backend only
docker compose -f docker-compose.prod.yml logs -f backend

# Frontend only
docker compose -f docker-compose.prod.yml logs -f frontend
```

### Resource Usage

For a typical deployment:

| Service | RAM | CPU |
|---------|-----|-----|
| Frontend | ~128 MB | Low |
| Backend | ~64 MB | Low |

The service is lightweight — it generates files and serves scripts, with no persistent workloads.
