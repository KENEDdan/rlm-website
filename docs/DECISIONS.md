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

## D-015: Sliders without a slider library
(2026-11-17) One reusable component (`templates/includes/slider.html` + `static/js/slider.js`) serves the home
hero, the card carousels (programmes, events, testimonies, branches, news, leaders), the album gallery and
its lightbox. CSS scroll-snap does the core work, so every slider works without JavaScript (swipe, scroll,
keyboard on the focusable track) and no third-party code was added; the ~4 KB vanilla module only adds
arrows, dots, keys, mouse drag, the hero autoplay (6 s, paused on hover/focus/touch, pause button, never with
reduced motion) and a `<dialog>` lightbox. Embla Carousel was considered and not needed. The hero is a
scroll-snap strip (slide transition) rather than a fade, so it degrades to a swipeable strip.
`HeroSlide` and `Partner` live in `core` (managed by Founder + Media & Communications only); button/partner
links accept only site-relative paths or `https://` (`core.validators.validate_safe_link`) and are
re-checked at render time. Testimonies gained an explicit **approved** flag and a name-display choice:
initials (default) or first name, full name only with recorded explicit consent. Existing published,
consented testimonies were migrated to approved; names were not carried over as full names.


## D-016: Staff portal with one dashboard per department (replaces the admin index as the landing page)
(2026-11-19) There was no M&E dashboard in the code; staff landed on the Django admin index. A new `portal`
app at `PORTAL_URL` (default `portal/`) is now where every staff member lands after the same password + TOTP
sign-in (2FA middleware, axes lockout, session timeout and audit log all apply to it). The Django admin stays
for website content (news, events, gallery, page text) and configuration.
* **Roles = the seven departments** from `docs/responsibilities.md`, plus Founder / Super Admin, Branch
  Coordinator and a new view-only **Executive Leadership** role. Groups were renamed (Secretary -> Membership
  Administration, Finance & Admin -> Finance & Resource Mobilization, Programs & Events -> Missions &
  Outreach); existing holders became department *members* (not heads). "Departmental Heads" and
  `User.department` were retired: a head is now `DepartmentMembership.is_head`. Former Departmental Heads
  keep their other roles and need a department from the Super Admin.
* **Department membership is the source of truth**; the Django group is derived from it by
  `accounts.services`, so the admin website-content permissions follow automatically.
* **Branch Coordinators** get branch-level access to Membership, Missions and Discipleship only, always
  limited to their branch; a coordinator without a branch sees nothing tied to a branch. The Branch
  Coordinator role restricts every department the person belongs to (simplest safe rule).
* **One declarative `Resource` registry** (`portal/resources.py`) drives every list/detail/form/delete/CSV
  screen. Scoping is written once: department level -> branch -> per-resource rule; out-of-scope objects are a
  404 (no IDOR); form dropdowns are limited to records the user may see and unknown related models get no
  choices at all; after saving, the record must still be inside the user's scope or the save is rolled back.
* **Charts are server-rendered SVG**, single-series in the brand hue with `<title>` tooltips and a data table.
  No Chart.js: nothing new to pin, no CSP change, works without JavaScript.
* **PDF = print-optimised report page** + the browser's "Save as PDF". No PDF library was added (it would be
  a new dependency with native libraries). Open question: whether the ministry needs server-generated PDFs.
* **Executive Overview** shows aggregate figures only. Executive Leadership sees totals for all departments
  but drill-down links appear only for departments they belong to.
* **M&E layer** (`Indicator`, `IndicatorValue`, `DepartmentReport`) was built with the shell (the overview
  needs it). Heads set targets; members record values; heads generate a monthly/quarterly/annual report from
  the dashboard (figures snapshot + indicator auto-fill via `auto_source`), add the narrative and submit; only
  the Super Admin reviews or returns it. Reports are due on `REPORT_DUE_DAY` (10th) of the next month.
* **Private uploads** (`core.private_files`) live in `PRIVATE_MEDIA_ROOT`, outside `MEDIA_ROOT`, and are only
  downloadable through a permission-checked, audit-logged portal view.

## D-017: Only the Super Admin manages accounts; invite-only onboarding
(2026-11-19) There was never public self-registration; a test now walks every URL pattern anonymously (GET
and POST with account-like data) and proves no user is created, and that no signup/social-login/API routes
exist.
* **Super Admin = active superuser.** Only `accounts.services` changes accounts or roles, and every function
  re-checks that the actor is an active Super Admin (not just the view). The Founder group no longer carries
  any account/role permission, so group membership alone can never manage accounts.
* **Django admin user screens are read-only for everyone, superusers included** (stricter than asked): the
  admin would bypass re-authentication, the Super Admin limit and last-Super-Admin protection. The admin's
  "set another user's password" screen was removed; users change their own password (logged as sanctioned).
* **Invites**: account created inactive with an unusable password; a single-use 256-bit token (only its
  SHA-256 is stored) is emailed to the address the Super Admin typed; valid `INVITE_TTL_HOURS` (48); resending
  revokes older links. The invitee chooses a password (validators apply) and is then forced through TOTP
  enrolment and backup codes before any page. Every invalid/expired/used/revoked link gets the same 404 page.
  Forced password reset uses the same mechanism; no password is ever emailed or displayed.
* **Re-authentication** (password + fresh TOTP) is required for every account screen that changes something,
  valid for `REAUTH_WINDOW_SECONDS` (5 minutes) in that session.
* **Safeguards**: `SUPER_ADMIN_LIMIT` (2); nobody edits their own account; the last active Super Admin cannot
  be demoted/deactivated/deleted; deactivation, deletion, 2FA reset and forced reset end all sessions at once;
  deletion is a soft delete (row and audit history kept, roles/2FA/password removed).
* **Detection, not just prevention**: a model-layer guard diffs every account/role change and writes it to the
  audit log with old and new values, actor and IP. A change made outside the services (e.g. a Django shell)
  is logged as "changed OUTSIDE the portal" and emails all Super Admins immediately. A 15-minute HMAC
  fingerprint check (keyed with SECRET_KEY, which is not in the database) also catches raw SQL edits.
* **Dormant accounts**: flagged after `DORMANT_FLAG_DAYS` (60), disabled after `DORMANT_DISABLE_DAYS` (90).
  Super Admins are flagged but never auto-disabled, so the ministry cannot be locked out.
* **Bootstrap**: `manage.py create_super_admin` (interactive, hidden password prompt) replaces
  `create_founder` and refuses to run once an active Super Admin exists.
