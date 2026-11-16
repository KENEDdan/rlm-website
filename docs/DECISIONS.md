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

## D-011: Page wording and form choices are data
(2026-11-16) Page headings, intros, SEO text, home sections, the CTA band and the footer blurb live in
`core.PageText`; public form choice lists live in `core.FormOption`. Defaults are in `core/page_texts.py`;
`migrate` creates missing rows without overwriting edits, and templates fall back to the defaults if a row
is missing. Option codes are immutable and options are deactivated rather than deleted, so old submissions
keep readable labels. Edit rights: Page text = Founder + Media & Communications; Form options = Founder +
Secretary. Neither can be deleted in the admin. Site settings also gained `logo_on_dark`; uploaded logos now
actually replace the built-in ones (previously the `logo` field was unused), and the header wordmark follows
the ministry name. Pages can be listed in the footer (`show_in_footer`).

## D-012: Production stack prepared and rehearsed locally (phase K)
(2026-11-16) `docker-compose.prod.yml`, `docker/Caddyfile`, `docker/backup/`, `scripts/deploy.sh` and
`scripts/server/setup-ubuntu.sh` were written and rehearsed on the PC with a throwaway `.env` (HTTPS on
`localhost:8443`); nothing was deployed (D-007). Choices: Caddy for automatic HTTPS; a separate `beat`
container (exactly one scheduler); `data` network `internal: true` so Postgres/Redis have no internet; Redis
password even on the private network; backups encrypted with **age** so only the public key lives on the
server; a dedicated backup image so the server needs nothing but Docker; rollback to the last image that
passed its health check (`rlm-web:good`). Lighthouse over HTTPS could not run against a self-signed
`localhost` certificate; the HTTPS checks were verified directly with header tests instead.

## D-013: Handover tooling (phase L)
(2026-11-16) `manage.py launch_check` turns the launch checklist into an automatic report (BLOCKER /
WARNING / OK, each with where to fix it; `--strict` fails while blockers remain). `manage.py create_founder`
replaces `createsuperuser` for the Founder: password validators enforced, Founder role added, audit-logged,
password only via a hidden prompt. The staff security sheet is a printable one-page HTML (`docs/`), checked
to print on a single A4 page. Contact lines on it are blank write-in fields: no phone numbers or emails in
the repository (rule 2).

## D-014: Cookies and privacy policy facts
(2026-11-16) The CSRF cookie became a browser-session cookie (`CSRF_COOKIE_AGE = None`), so the site sets no
long-lived cookies; visitors only receive strictly necessary cookies (CSRF on form pages, a one-off messages
cookie), which need no consent banner. The privacy page appends a generated section (cookie names from
settings, retention days from Site settings) so the policy cannot drift from reality. A footer "Privacy
choices" control lets visitors withdraw analytics consent (shown only when analytics is configured). A
fuller draft policy (third parties, legal basis, children, transfers, complaints) replaced the original
seed only where it was untouched; it remains a Draft for leadership (launch_check blocks until reviewed).
