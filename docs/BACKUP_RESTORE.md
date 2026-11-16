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

## 4. Production (built and rehearsed in phase K; runs once the server exists)

Backups use the `backup` service in `docker-compose.prod.yml` (image `docker/backup`): `pg_dump` + media
archive, **encrypted with age** using only the **public** key on the server, SHA-256 checksums, local
retention (`BACKUP_RETENTION_DAYS`, default 30) and an optional off-site copy with rclone
(`BACKUP_REMOTE`). Cron runs it nightly at 02:30 (`/etc/cron.d/rlm-backup`); `scripts/deploy.sh` also runs
it before every migration.

```bash
cd /srv/rlm
docker compose -f docker-compose.prod.yml run --rm backup          # manual backup
ls -l /srv/rlm/backups                                              # rlm-<time>-db.dump.age, -media.tgz.age, .sha256
```

### Restore test (monthly; does not touch live data)
The **private** age key comes from the password manager and is only mounted for the restore:
```bash
umask 077; nano /tmp/age.key                                        # paste the private key file
docker compose -f docker-compose.prod.yml run --rm --entrypoint restore.sh   -v /tmp/age.key:/run/secrets/age.key:ro backup db rlm-YYYYmmdd-HHMMSS-db.dump.age
shred -u /tmp/age.key
```
It verifies the checksum, restores into the scratch database `rlm_restore_test` and prints row counts.

### Real restore (disaster recovery)
```bash
docker compose -f docker-compose.prod.yml stop caddy web worker beat
CONFIRM_OVERWRITE=yes docker compose -f docker-compose.prod.yml run --rm --entrypoint restore.sh   -e CONFIRM_OVERWRITE -v /tmp/age.key:/run/secrets/age.key:ro backup db rlm-...-db.dump.age rlm
CONFIRM_OVERWRITE=yes docker compose -f docker-compose.prod.yml run --rm --entrypoint restore.sh   -e CONFIRM_OVERWRITE -v /tmp/age.key:/run/secrets/age.key:ro backup media rlm-...-media.tgz.age
docker compose -f docker-compose.prod.yml up -d
shred -u /tmp/age.key
```
The restore refuses to overwrite the live database or media unless `CONFIRM_OVERWRITE=yes` is given.
`.env` must hold the **same** `FIELD_ENCRYPTION_KEYS` / `BLIND_INDEX_KEY` as when the backup was taken.

### Off-site storage rules
* The server's storage key may **write** but not **delete** (protects against ransomware wiping backups).
* The bucket has its own lifecycle rule (e.g. 90 days).
* Keys (section 1) are never stored in the backup bucket.

Rehearsed on 2026-11-16 with the real image: encrypted backup, checksum, restore into a scratch database,
refusal to overwrite the live database without confirmation.
