#!/bin/sh
# Restore an encrypted backup. Needs the PRIVATE age key mounted at /run/secrets/age.key (never stored
# on the server permanently).
#   restore.sh db    rlm-YYYYmmdd-HHMMSS-db.dump.age   [target_db]   (default target: rlm_restore_test)
#   restore.sh media rlm-YYYYmmdd-HHMMSS-media.tgz.age              (replaces /media contents)
#   restore.sh private rlm-YYYYmmdd-HHMMSS-private.tgz.age          (adds the backed-up private files back)
set -eu
KEY=/run/secrets/age.key
[ -r "$KEY" ] || { echo "mount the private age key at $KEY" >&2; exit 2; }
KIND="${1:?db|media|private}"
FILE="/backups/${2:?backup file name}"
[ -f "$FILE" ] || { echo "no such backup: $FILE" >&2; exit 2; }
(cd /backups && grep " $(basename "$FILE")\$" rlm-*.sha256 | sha256sum -c -) || { echo "checksum mismatch" >&2; exit 3; }
export PGPASSWORD="$POSTGRES_PASSWORD"

case "$KIND" in
  db)
    TARGET="${3:-rlm_restore_test}"
    if [ "$TARGET" = "$POSTGRES_DB" ] && [ "${CONFIRM_OVERWRITE:-}" != "yes" ]; then
        echo "refusing to overwrite the live database; set CONFIRM_OVERWRITE=yes" >&2; exit 4
    fi
    psql -h db -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
        -c "DROP DATABASE IF EXISTS \"$TARGET\"" -c "CREATE DATABASE \"$TARGET\""
    age -d -i "$KEY" "$FILE" | pg_restore -h db -U "$POSTGRES_USER" -d "$TARGET" --no-owner --exit-on-error
    echo "restored into database $TARGET"
    psql -h db -U "$POSTGRES_USER" -d "$TARGET" -Atc \
        "select 'events', count(*) from events_event union all select 'audit log', count(*) from audit_auditlog"
    ;;
  media)
    [ "${CONFIRM_OVERWRITE:-}" = "yes" ] || { echo "set CONFIRM_OVERWRITE=yes to replace media" >&2; exit 4; }
    find /media -mindepth 1 -delete
    age -d -i "$KEY" "$FILE" | tar xzf - -C /media
    echo "media restored"
    ;;
  private)
    # Private uploads (receipts, permits, member documents). Files have random names, so extracting over the
    # existing folder restores every backed-up file without removing anything.
    [ "${CONFIRM_OVERWRITE:-}" = "yes" ] || { echo "set CONFIRM_OVERWRITE=yes to restore private files" >&2; exit 4; }
    age -d -i "$KEY" "$FILE" | tar xzf - -C /private
    echo "private files restored"
    ;;
  *) echo "first argument must be db, media or private" >&2; exit 2 ;;
esac
