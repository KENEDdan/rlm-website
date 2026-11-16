#!/usr/bin/env bash
# Deploy (or redeploy) the production stack on the server, from /srv/rlm.
#
#   scripts/deploy.sh             git pull, build, check, backup, migrate, start, verify, auto-rollback
#   scripts/deploy.sh --no-pull   same, using the code already on disk
#
# Rollback: if the new version is not healthy within 2 minutes, the last known-good image is restarted.
# Database migrations are NOT reversed automatically; a pre-deploy encrypted backup is taken first
# (docs/BACKUP_RESTORE.md) so the database can be restored if a migration has to be undone.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${RLM_ENV_FILE:-.env}"
export RLM_ENV_FILE="$ENV_FILE"  # docker-compose.prod.yml reads the same file for every service
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)
log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found (copy .env.production.example and fill it in)"
if [ "${RLM_ALLOW_INSECURE_ENV_PERMS:-0}" != "1" ]; then
    perms="$(stat -c %a "$ENV_FILE")"
    [ "$perms" = "600" ] || die "$ENV_FILE must be chmod 600 (it is $perms)"
fi
grep -q 'change-me' "$ENV_FILE" && die "$ENV_FILE still contains 'change-me' placeholders"

if [ "${1:-}" != "--no-pull" ]; then
    log "updating code"
    git pull --ff-only
fi
REV="$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)"

# rlm-web:good is only ever set after a deploy passed its health check, so a rollback always returns
# to a version that really worked (never to a half-finished earlier attempt).
if docker image inspect rlm-web:good >/dev/null 2>&1; then HAVE_GOOD=1; else HAVE_GOOD=0; fi

log "building $REV"
"${COMPOSE[@]}" build web backup
docker tag rlm-web:prod "rlm-web:$REV"

log "configuration check (check --deploy)"
"${COMPOSE[@]}" run --rm --no-deps migrate python manage.py check --deploy --fail-level WARNING

if [ -n "$("${COMPOSE[@]}" ps -q db 2>/dev/null)" ]; then
    log "encrypted backup before migrating"
    "${COMPOSE[@]}" run --rm backup
fi

log "migrating database"
"${COMPOSE[@]}" run --rm migrate

log "starting containers"
# 'up' itself fails when web never becomes healthy (caddy waits for it); that must lead to the
# rollback below, not abort the script.
"${COMPOSE[@]}" up -d --remove-orphans || log "compose reported a problem; checking web health"

log "waiting for the web container to become healthy"
status="starting"
for _ in $(seq 1 60); do
    cid="$("${COMPOSE[@]}" ps -q web)"
    status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo missing)"
    [ "$status" = "healthy" ] && break
    sleep 2
done

if [ "$status" != "healthy" ]; then
    log "new version is $status: last web logs follow"
    "${COMPOSE[@]}" logs --tail 40 web || true
    if [ "$HAVE_GOOD" = "1" ]; then
        log "ROLLING BACK to the last known-good image"
        docker tag rlm-web:good rlm-web:prod
        "${COMPOSE[@]}" up -d --no-build --wait || log "WARNING: check 'docker compose ps' after rollback"
        die "deploy of $REV failed and was rolled back (migrations, if any, remain applied)"
    fi
    die "first deploy of $REV failed; nothing to roll back to"
fi

docker tag rlm-web:prod rlm-web:good

docker image prune -f >/dev/null
log "deployed $REV successfully"
