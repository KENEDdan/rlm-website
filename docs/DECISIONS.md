# Decision log

Each entry: what was decided, why, and what (if anything) the ministry must confirm later.

## D-001: Brief missing; placeholder content only
`docs/RLM_website_details.docx` / `.md` were not in the repository or anywhere on the build machine. Only
`CLAUDE.md`, the build playbook and the logos were available. All ministry copy (vision, mission, programme
descriptions, about text) is therefore **neutral placeholder text**, seeded once and fully editable in the admin.
Programmes were seeded from the giving categories named in the playbook. **Action:** ministry to replace copy
from the official brief.

## D-002: Standalone git repository
The folder sat inside an unrelated parent repository (`~/projects`). A separate repo was initialised in
`rlm-website/` so no other project's files can be committed by accident.

## D-003: Django 5.2 LTS
CLAUDE.md asks for "Django 5.x (LTS if available)". 5.2 is the current LTS (security support to April 2028),
so it is used rather than 6.x.

## D-004: Third-party packages
The user asked for autonomous work, so packages were chosen without a separate approval round. Each one is
listed here with its reason. All are actively maintained, widely used and hash-pinned.

| Package | Why |
|---|---|
| django-environ | env-based settings (requested) |
| psycopg[binary] 3 | PostgreSQL driver |
| gunicorn, whitenoise | app server and compressed, cache-busted static files |
| celery, redis | background email jobs (requested) |
| argon2-cffi | Argon2 hashing (rule 4) |
| django-axes | login lockout (rule 4) |
| django-ratelimit | per-IP form and login limits (rule 7) |
| django-csp 4 | CSP with nonces (rule 9) |
| django-otp, qrcode | TOTP 2FA + backup codes; QR rendered as SVG (no image deps) |
| cryptography | Fernet / MultiFernet field encryption (rule 3) |
| Pillow, python-magic | image re-encoding / EXIF stripping and content sniffing (rule 8) |
| sentry-sdk | optional error reporting, enabled only when `SENTRY_DSN` is set, PII scrubbed |
| dev: pytest, pytest-django, pytest-cov, ruff, black, bandit, pip-audit, pre-commit, detect-secrets, pip-tools | tests, lint, audit, hash pinning |

**Not added:** django-two-factor-auth (a small in-house flow on top of django-otp gives full control and fewer
deps); django-unfold (its Alpine.js runtime needs `unsafe-eval`, which conflicts with the strict CSP). The stock
admin is themed with brand CSS variables instead (see D-006).

## D-005: Rich text
Admin-entered bodies are plain text rendered with Django's `linebreaks` filter (auto-escaped). No HTML or
Markdown is accepted, so `|safe` is never needed for content (rule 7). A Markdown and nh3 sanitiser can be
added later if editors need headings or links.

## D-006: Admin theme
The Django admin is themed with the brand tokens through its built-in CSS variables
(`static/admin/rlm-admin.css`). No JS framework is involved, so it stays CSP-compatible.

## D-007: Local only until the ministry creates the repository
(2026-11-16) The site runs only on the developer PC with Docker. No remote repository, server, domain or
deployment exists. `docs/DEPLOYMENT.md` is a plan for phase K, not a runbook. **Action:** ministry creates
and owns the GitHub organisation and hosting accounts first.

## D-008: Tooling run in throwaway containers, not installed on the PC
Trivy (image scan) and Lighthouse (Node + Chromium) ran in disposable Docker containers, so no Node runtime or
scanner is installed on the PC and the project keeps "no Node in prod". Lighthouse was run against the
**production image behind a local Caddy** (mirroring phase K), because the dev `runserver` serves
uncompressed, uncached files and would misreport performance.

## D-009: Demo data
`manage.py seed_demo` creates clearly fake content (titles start with "DEMO", `demo-` slugs, `@example.test`
addresses, generated flame-gradient placeholder images marked "DEMO PLACEHOLDER"). It refuses to run when
`DEBUG` is off and `--reset` removes only what it created. The placeholder video is a public sample
(Big Buck Bunny) and must never be published on the real site.

## D-010: Data-subject requests via command line
`manage.py personal_data` answers export/erase requests (rule 13). Donations are anonymised, not deleted,
so accounting records stay complete. **Open question:** a Founder-only admin screen for the same task.
