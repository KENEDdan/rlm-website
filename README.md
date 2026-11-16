# Rebuilding Lives Ministry — website

*Rebuilding Lives. Reviving Generations.* (Acts 15:16)

The ministry's "connection centre": information, events and registration, volunteering, prayer requests,
contact, newsletter, partnership, sermons and resources, gallery, news and giving. Every branch, programme,
leader, event and page is data managed in the admin, so a new branch or country needs no code change.

> **Status:** runs locally only (Docker on a PC). Production deployment is a later phase; see
> `docs/DEPLOYMENT.md` (a plan, nothing is deployed yet).

## Stack

Python 3.12 · Django 5.2 LTS · PostgreSQL 16 · Redis + Celery (email/background jobs) · Django templates +
Tailwind (standalone CLI, no Node) + HTMX · Gunicorn + WhiteNoise · Docker Compose.

## Run it on your PC

Requirements: Docker Desktop (start it first) and Git.

```bash
# 1. Create your local secrets file (never commit it)
python scripts/generate_env.py > .env        # or copy .env.example and fill every value

# 2. Build and start: web, worker, Postgres, Redis, Mailpit
docker compose up -d --build

# 3. Create the first staff account (the Founder)
docker compose exec web python manage.py createsuperuser

# 4. Optional: fake demo content so every page has something to show
docker compose exec web python manage.py seed_demo
```

| What | Where |
|---|---|
| Website | http://localhost:8010 |
| Staff area | http://localhost:8010/`<DJANGO_ADMIN_URL>`account/login/ (value from `.env`; `/admin/` is a 404 on purpose) |
| Emails sent by the site (Mailpit) | http://localhost:8026 |

The first staff sign-in asks you to scan a QR code with an authenticator app (Google Authenticator,
Microsoft Authenticator, Authy, 1Password…). Two-factor sign-in is mandatory for every staff account.

Remove demo content with `docker compose exec web python manage.py seed_demo --reset`.

### Rebuilding CSS while editing templates

```bash
docker compose --profile css up css        # Tailwind watcher, writes static/css/site.css
```

## Everyday commands

```bash
docker compose exec web pytest                                  # tests (1100+), coverage gate 85%
docker compose exec web ruff check . && docker compose exec web black --check .
docker compose exec web bandit -c pyproject.toml -r . -q
docker compose exec web pip-audit -r requirements/base.txt
docker compose exec web python manage.py check --deploy --settings=config.settings.prod
docker compose exec web python manage.py makemigrations --check --dry-run
```

### Maintenance commands

| Command | Purpose |
|---|---|
| `manage.py sync_roles` | Re-create the 7 staff roles and their permissions (idempotent) |
| `manage.py seed_demo [--reset] [--no-images]` | Fake demo content; refuses to run when `DEBUG` is off |
| `manage.py personal_data find\|export\|erase --email …` | Answer a person's request to see or delete their data |
| `manage.py rotate_encryption_keys [--dry-run]` | Re-encrypt personal data with a new key (see `docs/BACKUP_RESTORE.md`) |

## Project layout

| Path | Contents |
|---|---|
| `config/` | settings (`base`, `dev`, `test`, `prod`), URLs, Celery |
| `core/` | site settings, encryption, uploads, form protection, audit helpers, privacy tools |
| `accounts/` | staff users, roles, mandatory 2FA |
| `branches/ programs/ leadership/ events/ registrations/ prayer/ contact/ newsletter/ media_library/ resources/ news/ giving/ audit/` | one app per area |
| `templates/`, `static/` | pages, brand assets, Tailwind input |
| `tests/` | pytest suite (permission matrix, forms, encryption, giving, security regressions) |
| `docs/` | plan, decisions, security audit, guides |

## Security in one paragraph

Personal data (prayer requests, volunteer details, donors, contacts) is encrypted in the database, and
emails are matched through keyed hashes. Staff need a 12+ character password **and** an authenticator code;
each role sees only its own area, and Branch Coordinators only their branch. Viewing, exporting and changing
sensitive records is written to an append-only audit log. Public forms have CSRF, rate limits, a honeypot and
Cloudflare Turnstile. Card data is never handled by this site. Details: `CLAUDE.md` (rules) and
`docs/SECURITY_AUDIT.md`.

**Never commit `.env`, database dumps or anything containing personal or bank data.** Bank details are typed
into the admin by Finance, never into code.

## Documentation

| Document | For |
|---|---|
| `docs/ADMIN_GUIDE.md` | Staff: step-by-step tasks per role |
| `docs/BACKUP_RESTORE.md` | Backups, restore, key safekeeping and rotation |
| `docs/INCIDENT_RESPONSE.md` | What to do if an account or the computer/server is compromised |
| `docs/DEPLOYMENT.md` | The later move to a server (plan only) |
| `docs/GIVING_GATEWAYS.md` | Choosing an online payment gateway |
| `docs/SECURITY_AUDIT.md` | Phase I audit results |
| `docs/PLAN.md`, `docs/DECISIONS.md` | Architecture and decision log |
