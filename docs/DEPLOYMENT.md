# Production deployment — IT Talent AI Profile

## Scope and audit

The existing `docker-compose.yml` and both development Dockerfiles are unchanged.
Development uses source bind mounts, Uvicorn reload, Vite dev server and host-loopback DB/Redis ports. Production uses separate images and project-scoped volumes, a static Vite build served by Nginx, and a one-shot Alembic migration. All eight services remain: postgres, redis, clamav, migrate, backend, worker, maintenance, frontend.

```text
Internet :80/:443 -> Caddy (Linux host; TLS) -> 127.0.0.1:8080
   -> Nginx (static UI; /api/* -> backend:8000)
   -> FastAPI -> PostgreSQL / Redis (isolated data network)
              -> ClamAV (scanner network)
              -> GitHub / AI provider (outbound network)
   Redis -> RQ worker + maintenance -> PostgreSQL
```

Only frontend publishes a loopback host port. Caddy is an optional host component for local smoke tests but HTTPS is required for real production access and login. The app already sets Secure/HttpOnly/SameSite=Lax OAuth/session cookies in production and disables Swagger/OpenAPI. No JWT secret is used by this session flow. The proxy preserves /api/v1 paths; it does not strip the prefix. Uvicorn access logging is disabled to avoid OAuth codes in query strings; Nginx logs method/path/status without query string and Caddy access logging is not enabled. Forwarded client IP is deliberately not trusted by Uvicorn; public URLs are configured explicitly. If client IP or request scheme is required by a future feature, configure trusted proxy addresses explicitly, never trust arbitrary clients.

## Prerequisites

Docker Engine / Desktop with Compose v2, Git, free disk space, and available loopback port 8080. Use Linux for a public deployment, with a domain and Caddy installed on the host. Start with a single API worker and one RQ worker; size memory for PostgreSQL, ClamAV signatures and any local AI model. Monitor real resource usage before increasing concurrency. Use a supported OS and regularly rebuild/pin reviewed image versions/digests and dependencies; current image tags are not immutable.

## Secrets and environment

Copy the template without overwriting an existing production file.

PowerShell (local smoke test):

```powershell
if (-not (Test-Path .env.production)) { Copy-Item .env.production.example .env.production }
```

Linux (private file):

```bash
umask 077
test -e .env.production || cp .env.production.example .env.production
chmod 600 .env.production
openssl rand -hex 32
python3 -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Put the first generated value in POSTGRES_PASSWORD (hex avoids URL-escaping problems), the second in GITHUB_TOKEN_ENCRYPTION_KEY. Never put actual values in Git, frontend variables or screenshots. Generate once per independent environment; preserve the encryption key securely with backups. Rotating it without a data migration can invalidate encrypted GitHub tokens and CV receipts. Compose passes secrets as container environment variables; Docker administrators can inspect them, so limit host access. A managed secret store is a future option (the current application does not implement *_FILE variables). Shell variables take precedence over the env file: clear conflicting development variables before launching. Never print expanded `docker compose config` with real secrets; use `config --quiet`.

Set FRONTEND_URL and CORS_ORIGINS to the actual public origin (no trailing slash), and GITHUB_REDIRECT_URI to that origin + /api/v1/auth/github/callback. Register a separate GitHub OAuth App with this exact callback. Configure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET. For local HTTP health checks OAuth need not be configured; for local UI use http://localhost:8080 as the origin and matching callback, but verify authentication on HTTPS (Secure cookies).

AI defaults mirror the existing Compose setup (Ollama, qwen2.5:3b). Pull the selected model on the Ollama host, and ensure backend/worker can reach AI_BASE_URL. Linux host-gateway support is configured; the Ollama listener must accept the Docker bridge connection, not only host loopback. Restrict the listener by firewall/private network; do not expose unauthenticated Ollama publicly. Alternatively select the existing openai or gemini provider and configure its supported model/key. Verify actual AI requests; health only checks PostgreSQL and Redis.

## Run without affecting development

All commands from repository root. Never combine the dev and prod Compose files with multiple -f arguments. Use a dedicated project name (ita-prod), no external volumes, and a free PROD_HTTP_PORT. This initializes a new production DB; it does not migrate data from development. Do not reuse development credentials/volumes.

PowerShell or Linux:

```sh
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml build
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml up -d
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml ps -a
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml logs --tail 100 migrate
```

Migration must exit 0 before backend/worker/maintenance start. PostgreSQL, Redis, backend, frontend and ClamAV have health checks; worker and maintenance restart on process exit but require functional checks. An unhealthy container is not automatically restarted by Compose solely because of health status.

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/health
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml exec backend alembic current
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml exec backend alembic heads
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml exec backend python -m app.workers.enqueue ping --message prod-smoke --wait 15
```

Linux health check: `curl -fsS http://127.0.0.1:8080/api/v1/health`. Verify DB and Redis both ok, Alembic current equals heads, worker returns pong, and ClamAV becomes healthy. Browser login, analysis, scoring, roadmap, AI Mentor, CV Studio/matching and logout require separate functional tests. CV raw preview is limited to 5 MiB by the app; proxy allows 16 MiB to avoid reducing app limits (including other JSON requests). Proxy response timeout is 300s, streaming buffering disabled; review if application timeouts are increased.

Development command remains `docker compose up -d --build` in its original directory/env.

## Public server and HTTPS

Point DNS A/AAAA records to the host (only configure AAAA when IPv6 works). Allow public TCP 80/443 to Caddy and restricted SSH access. Do not expose 8080, 8000, 5432, 6379, 3310, or 11434. Install Caddy from its official distribution, adapt deploy/Caddyfile to the real domain and loopback port, and install as /etc/caddy/Caddyfile. Validate and reload:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
curl -fsS https://profile.example.com/api/v1/health
```

Caddy obtains/renews TLS certificates and redirects HTTP to HTTPS when DNS, network and certificate issuance work. Test HTTP redirect, certificate, OAuth callback and Secure cookies in a browser. Do not publish the service before these checks pass. HSTS is set to one day initially; increase only after verifying stable HTTPS. Configure application-level/edge rate limits and abuse controls before broad public access as needed. This is single-host deployment, not HA.

## Monitoring and operations

```sh
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml ps -a
docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml logs --tail 100 backend worker maintenance clamav
docker stats --no-stream
docker system df
```

Linux: `df -h`, `free -h`, `journalctl -u caddy --since today`. JSON log rotation limits each container to about 50 MB. Nginx logs path/status without query; critical proxy errors still need restricted access and review. Do not expose logs publicly. Monitor health status, HTTP 5xx, worker failed/queued jobs, maintenance warnings, disk space, RAM, ClamAV signature freshness and AI timeouts. Set alerts and a periodic external HTTPS health check; no external monitoring service is provisioned here.

## Backup and restore (Linux server)

PostgreSQL includes confirmed CV text in ita.cvs JSONB, profile/evidence and other business records. CV preview raw files are processed in memory; no raw upload volume is configured. Redis AOF stores session/job state; it is not the authoritative database. ClamAV signatures are re-downloadable. analysis_temp is sensitive temporary source code: do not routinely archive it; allow maintenance cleanup. Preserve the encryption key and environment configuration separately in encrypted storage.

Run daily with a restricted account, off-host encrypted copies, retention (e.g. daily 7, weekly 4), and restore drills. Example manual backup:

```bash
umask 077
mkdir -p backups
backup="backups/ita-$(date -u +%Y%m%dT%H%M%SZ).dump"
if docker compose -p ita-prod --env-file .env.production -f docker-compose.prod.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup.partial"; then
  mv "$backup.partial" "$backup"
else
  rm -f "$backup.partial"
  exit 1
fi
```

Do not redirect binary dump through Windows PowerShell 5.1 (can corrupt output); use Linux or write inside the container and docker cp. Restore only into a fresh isolated PostgreSQL 17 database, not the live DB. Example (new restore_check database in an isolated PostgreSQL instance named restore-postgres, with appropriate credentials):

```bash
docker exec restore-postgres createdb -U ita restore_check
docker exec -i restore-postgres pg_restore -U ita -d restore_check --exit-on-error --no-owner < "$backup"
docker exec restore-postgres psql -U ita -d restore_check -c 'SELECT * FROM ita.alembic_version;'
```

Verify counts and a functional sample with the matching release and encryption key in a non-public test stack. Do not restore Redis from a different DB snapshot blindly; generally invalidate sessions and reconcile jobs, or restore coordinated snapshots when required. Record actual RPO/RTO from tests.

## Deployment updates and rollback

Tag both images with a unique release SHA via ITA_IMAGE_TAG, retain previous images and corresponding Compose/env config securely. Before upgrades, stop accepting traffic, drain jobs and stop backend/worker/maintenance; make a verified DB backup. Build reviewed release, run Compose up, check migration exit status then smoke test. Restore public traffic only after successful tests. If rollback needed, use previous release images/config; migration may not be backwards-compatible, so restore a verified pre-upgrade database in isolation and plan cutover, not a blind downgrade. Never use `down -v`, `volume prune` or destructive restore against live data. A regular `down` preserves volumes.

## Acceptance checklist

| Check | Expected |
| --- | --- |
| Dev compose | Original command/config unchanged |
| Prod config | Compose config --quiet exits 0 |
| Build | Both Dockerfiles build; frontend dist served |
| Processes | No Vite dev server or reload; non-root backend |
| Network | Only frontend published on loopback; data services internal |
| Migration | Exit 0, current equals heads |
| API | Root UI and /api/v1/health via proxy, 200; docs disabled in production |
| Worker/maintenance | Ping finished, maintenance running; analysis job completes |
| ClamAV/CV | Scanner healthy, valid CV accepted, invalid/oversize rejected |
| Auth | HTTPS, exact callback, login/logout, Secure cookies |
| Core features | Analysis, scoring, roadmap, mentor, CV smoke tests |
| Persistence | Restart preserves DB/Redis data |
| Backup | Successful isolated restore and verification |
| Operations | Log rotation and alerts reviewed |

Status at initial change: source/config review only; Docker build, runtime checks, public TLS, OAuth, AI and recovery must be verified on a Docker-enabled host before declaring production-ready.
