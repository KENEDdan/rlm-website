# Backup and restore

> **Now:** the site runs only on a local PC with demo data. Section 2 is what to do on the PC.
> **Later:** when real people's data is collected on a server, section 4 (automated encrypted off-site
> backups) becomes **mandatory** and is built in phase K.

## 1. What must be backed up, and why

| Item | Where | Without it |
|---|---|---|
| PostgreSQL database | Docker volume `rlm_pgdata` | all content and submissions lost |
| Uploaded media | Docker volume `rlm_media` | photos, posters, PDFs, audio lost |
| **Encryption keys** `FIELD_ENCRYPTION_KEYS` and `BLIND_INDEX_KEY` | `.env` | **every prayer request, volunteer, donor and contact record is unreadable forever**, even with a perfect database backup |
| `DJANGO_SECRET_KEY`, `DJANGO_ADMIN_URL` | `.env` | sessions/links reset (recoverable) |

Keep the keys **apart from** the database backups. Someone holding both can read the personal data, and
someone holding only one cannot. Store them in a password manager (for example the Founder's and one trusted
deputy's), or printed in a sealed envelope in a safe. Never in email, chat, cloud notes or the Git
repository.

## 2. On the local PC (now)

Run from the project folder in **Git Bash**. `backups/` is ignored by Git, so dumps can never be committed.
`MSYS_NO_PATHCONV=1` and `$(pwd -W)` stop Git Bash from rewriting the container paths (`/out`, `/in`).

### Backup
```bash
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M)
# Database (custom format: compressed, restorable table by table)
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
  > "backups/rlm-db-$STAMP.dump"
# Media
MSYS_NO_PATHCONV=1 docker run --rm -v rlm_media:/media:ro -v "$(pwd -W)/backups:/out" alpine:3.20 \
  tar czf "/out/rlm-media-$STAMP.tgz" -C /media .
```
If the dump will leave the PC (USB stick, cloud), encrypt it first, e.g. 7-Zip with AES-256 and a strong
password kept in the password manager.

### Restore (replaces the current local data)
```bash
docker compose stop web worker
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < backups/rlm-db-STAMP.dump
MSYS_NO_PATHCONV=1 docker run --rm -v rlm_media:/media -v "$(pwd -W)/backups:/in:ro" alpine:3.20 \
  sh -c 'rm -rf /media/* && tar xzf /in/rlm-media-STAMP.tgz -C /media'
docker compose start web worker
```
The `.env` used must contain the **same** `FIELD_ENCRYPTION_KEYS` and `BLIND_INDEX_KEY` as when the backup
was made (or a key list that includes them).

### Test a backup without touching live data
```bash
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" rlm_restore_test'
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d rlm_restore_test --no-owner' < backups/rlm-db-STAMP.dump
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d rlm_restore_test -c "select count(*) from events_event"'
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" rlm_restore_test'
```
The database and media commands were tested on 2026-11-16 (rows, media files and the audit log's
append-only triggers restored correctly).

## 3. Encryption key rotation

Rotate when a key may have leaked (`docs/INCIDENT_RESPONSE.md`), when someone who knew it leaves, or
yearly.

1. **Back up first** (section 2 or 4) and keep the old `.env`.
2. Generate a key: `docker compose exec web python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
3. In `.env`, put the new key **first**: `FIELD_ENCRYPTION_KEYS=NEW_KEY,OLD_KEY`. To rotate the blind-index
   key too, replace `BLIND_INDEX_KEY` now.
4. Restart: `docker compose up -d`.
5. Check: `docker compose exec web python manage.py rotate_encryption_keys --dry-run`
6. Rotate: `docker compose exec web python manage.py rotate_encryption_keys`
   It stops **without changing anything** if a row cannot be decrypted (a key is missing).
7. Remove `OLD_KEY` from `.env`, restart, open a few prayer requests in the admin to confirm they read.
8. Update the stored copy of the keys (section 1). Old backups still need the **old** key, so keep it
   with those backups until they expire.

`DJANGO_SECRET_KEY` can simply be replaced; everyone is signed out, and unused newsletter
confirmation/unsubscribe links stop working.

## 4. Production (phase K, not built yet)

* Nightly `pg_dump` + media archive, **encrypted** (restic or age) before leaving the server.
* Copied to off-site storage owned by the ministry; 30 days of daily copies plus monthly copies.
* Restore tested monthly into a scratch database with a written check, and after every major upgrade.
* Backup credentials different from server credentials; the backup storage must not allow the server to
  delete old backups (protects against ransomware).
* Keys handled as in section 1, never stored in the backup bucket.
