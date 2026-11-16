# Rebuilding Lives Ministry (RLM) — Website

Tagline: "Rebuilding Lives. Reviving Generations." Scripture theme: Acts 15:16.
Branches: Juba and Yei (South Sudan). More branches/countries will be added later.
Full brief: `docs/RLM_website_details.md` (read it before any feature work).

## Purpose
A ministry "connection centre": information, events + registration, volunteer sign-up,
prayer requests, contact, newsletter, partnership enquiries, sermons/resources,
media gallery, news, and online giving. Must grow (new branch/programme/country)
WITHOUT code changes or redesign — everything is data managed in the admin.

## Stack
- Python 3.12, Django 5.x (LTS if available), PostgreSQL 16, Docker Compose
- Server-rendered Django templates + Tailwind CSS (standalone CLI, no Node runtime in prod) + HTMX
- Gunicorn behind Caddy (automatic HTTPS) in production; WhiteNoise for static files
- Redis + Celery only for email and background jobs
- Settings split: `config/settings/{base,dev,prod}.py`, all secrets via environment variables

## Apps (one Django app each)
core, accounts, branches, programs, events, registrations (volunteer, event),
prayer, contact, newsletter, media_library, resources (sermons/devotionals),
news, giving (partnership + donations), leadership, audit

## SECURITY RULES — NON-NEGOTIABLE
1. NEVER commit secrets, `.env`, database dumps, or personal/financial data. Only `.env.example` with fake values.
2. NEVER hardcode bank/account numbers, SWIFT codes, phone numbers or emails in code, templates or fixtures.
   They live in a `SiteSettings` / `GivingSettings` model editable in admin by Founder/Finance only.
3. Sensitive fields (prayer request text, volunteer testimony, phone, email, church affiliation, any PII)
   are encrypted at rest with field-level encryption (Fernet key from env, key rotation supported).
4. Admin: custom non-default URL, mandatory 2FA (TOTP) for every staff user, login rate limiting + lockout
   (django-axes), Argon2 password hashing, 12+ char password validators, session timeout.
5. Role-based access via Django Groups with least privilege (see Roles). Every admin queryset and view
   enforces object/section permissions. No staff user sees data outside their role.
6. Audit log (who viewed/exported/changed/deleted sensitive records) — append-only.
7. All forms: CSRF, server-side validation, rate limiting, honeypot + Cloudflare Turnstile, no raw SQL,
   no `|safe` / `mark_safe` on user input, output auto-escaped.
8. File uploads: whitelist extension AND verify content type (python-magic), size caps, random filenames,
   strip EXIF/GPS from images, re-encode images (Pillow), store outside web root; private files served via
   permission-checked views only.
9. Production headers: HTTPS only, HSTS (preload), secure + HttpOnly + SameSite cookies, strict CSP
   (django-csp, nonces, no inline scripts), X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
10. Containers: non-root user, read-only filesystem where possible, no secrets in images, pinned versions,
    DB and Redis NOT exposed publicly, only the reverse proxy listens on 80/443.
11. Payments: never store card data. Use hosted checkout of an approved gateway only (PCI scope stays with the gateway).
    Verify webhook signatures. Idempotent payment handling.
12. Dependencies pinned (hashes), `pip-audit` + `bandit` + `ruff` in CI; Dependabot enabled.
13. Privacy: privacy policy + cookie/consent notice, data retention periods, ability to export/delete a person's data.
14. Errors: DEBUG=False in prod, generic error pages, Sentry/logging with PII scrubbed.
15. If a requested feature conflicts with these rules, STOP and ask — do not weaken security silently.

## Roles (Django Groups)
- Founder / Super Admin: everything incl. users, giving settings, audit log
- Secretary: contacts, prayer requests, volunteers, events, news
- Finance & Admin: giving/partnership data and settings only
- Programs & Events: programmes, events, event registrations
- Media & Communications: gallery, sermons/resources, news, social links
- Branch Coordinator: only their own branch's data
- Departmental Heads: scoped to their department's content

## Conventions
- Type hints, ruff + black, small views, business logic in `services.py`
- Every model: `created_at`, `updated_at`; user-facing content has `is_published`, `slug`, SEO fields
- Tests with pytest-django; every permission rule and every form needs tests. Target >85% coverage on security-relevant code
- Mobile-first, fast on slow connections: WebP/AVIF thumbnails, lazy loading, minimal JS, Lighthouse perf >90
- Brand colours come from the official logo (sampled from the file). Use these as CSS variables / Tailwind theme tokens, never ad-hoc hex values:
  - `--rlm-black: #0A0A0A` (book + wordmark; page dark surfaces)
  - `--rlm-flame: #F0652A` (primary flame orange; buttons, links, accents)
  - `--rlm-flame-deep: #EE362C` (flame red; hover/active, gradient end)
  - `--rlm-amber: #F3A831` (secondary accent)
  - `--rlm-gold: #F8C124` (flame tip; highlights, gradient start)
  - `--rlm-flame-gradient: linear-gradient(135deg, #F8C124 0%, #F0652A 55%, #EE362C 100%)` (hero accents, section dividers, CTA glow)
  - Neutrals: white `#FFFFFF`, warm off-white `#FFF8F2`, greys `#1C1C1C`, `#6B6B6B`, `#E8E8E8`
  - Contrast rule: text on flame orange must be BLACK (white on #F0652A is only ~3.2:1 and fails AA); orange text on black is fine (~6:1). For white-on-orange buttons use a darker `#C2410C`.
  - Logo files in `static/brand/`: `logo-transparent.png` (light backgrounds), `logo-on-dark.png` (dark backgrounds). Convert to SVG/WebP variants and favicon set when building.
- Accessibility: semantic HTML, alt text, keyboard navigation

## Commands
- `docker compose up --build` — run dev stack
- `docker compose exec web python manage.py migrate | createsuperuser | test`
- `docker compose exec web pytest`
- `docker compose exec web ruff check . && bandit -r . && pip-audit`
- `docker compose exec web python manage.py check --deploy`

## Working agreements
- Work in small phases; after each phase: run tests, run linters, summarize what changed, list open questions.
- Commit after each phase with a clear message (never commit secrets).
- Ask before adding any new third-party package; explain why it is needed and its maintenance status.
- Placeholders for unknown items (logo, domain, social links, payment gateway) must be configurable in admin, not hardcoded.
