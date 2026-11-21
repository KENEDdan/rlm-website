#!/bin/sh
# Nightly backup: encrypted database dump + encrypted media and private-files archives, retention,
# optional off-site copy.
# Only the PUBLIC age key is on the server (BACKUP_AGE_RECIPIENT); the private key that can decrypt
# backups is kept off the server by the ministry (docs/BACKUP_RESTORE.md).
set -eu

: "${BACKUP_AGE_RECIPIENT:?set BACKUP_AGE_RECIPIENT (age public key) in .env}"
: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
OUT=/backups
STAMP="$(date -u +%Y%m%d-%H%M%S)"
umask 077

export PGPASSWORD="$POSTGRES_PASSWORD"

# Record the result for the Website dashboard (core.BackupRun): no file names, sizes or secrets, just ok/failed.
record_run() {
    psql -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -v ON_ERROR_STOP=1         -c "INSERT INTO core_backuprun (finished_at, ok, detail) VALUES (now(), $1, '$2')" >/dev/null 2>&1 || true
}
trap 'record_run false "backup failed"' EXIT
DB_FILE="$OUT/rlm-$STAMP-db.dump.age"
MEDIA_FILE="$OUT/rlm-$STAMP-media.tgz.age"
PRIVATE_FILE="$OUT/rlm-$STAMP-private.tgz.age"

pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner | age -r "$BACKUP_AGE_RECIPIENT" > "$DB_FILE.part"
mv "$DB_FILE.part" "$DB_FILE"
tar czf - -C /media . | age -r "$BACKUP_AGE_RECIPIENT" > "$MEDIA_FILE.part"
mv "$MEDIA_FILE.part" "$MEDIA_FILE"
tar czf - -C /private . | age -r "$BACKUP_AGE_RECIPIENT" > "$PRIVATE_FILE.part"
mv "$PRIVATE_FILE.part" "$PRIVATE_FILE"
(cd "$OUT" && sha256sum "$(basename "$DB_FILE")" "$(basename "$MEDIA_FILE")" "$(basename "$PRIVATE_FILE")" > "rlm-$STAMP.sha256")

# Local retention
find "$OUT" -maxdepth 1 -name 'rlm-*' -type f -mtime +"$RETENTION_DAYS" -delete

# Off-site copy (configure an rclone remote in /config/rclone/rclone.conf and set BACKUP_REMOTE)
if [ -n "${BACKUP_REMOTE:-}" ]; then
    rclone --config /config/rclone/rclone.conf copy "$OUT" "$BACKUP_REMOTE" --include "rlm-$STAMP*"
fi

trap - EXIT
record_run true "database, media and private files"
echo "backup ok: $(basename "$DB_FILE") $(basename "$MEDIA_FILE") $(basename "$PRIVATE_FILE")"
