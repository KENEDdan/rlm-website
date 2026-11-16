# RLM Website — Claude Code Playbook

Paste each prompt into Claude Code ONE AT A TIME. Wait for it to finish, run the checks, review the diff, then continue.
Tip: press `Shift+Tab` to use **Plan mode** for Phases 1, 5, 6 and 11 so Claude shows its plan before touching files.

---

## PHASE 0 — Terminal setup (you run these, not Claude)

```bash
mkdir rlm-website && cd rlm-website
git init
mkdir docs
mkdir -p static/brand
# Put logo-transparent.png and logo-on-dark.png (provided) into static/brand/
# Put CLAUDE.md in the project root, and the brief in docs/
# IMPORTANT: before saving the brief, DELETE the bank account number and SWIFT line from it.
# Bank details go into the admin panel later, never into the repo.
code .
claude
```

Inside Claude Code run `/init` once (it will respect the CLAUDE.md you placed), then:

---

## PHASE 1 — Read the brief and plan (Plan mode)

```
Read CLAUDE.md and docs/RLM_website_details.md carefully. Do not write code yet.
Produce a plan in docs/PLAN.md containing:
1. The full list of Django apps and their models (fields, relations, which fields are encrypted).
2. URL map for every required page in the brief.
3. Role/permission matrix for the roles in CLAUDE.md.
4. A threat model: assets (prayer requests, volunteer PII, donor data, admin accounts), likely threats, and the mitigation for each.
5. Items that are unknown (logo, domain, social links, payment gateway) and how each will be made configurable.
6. Phased build order.
Ask me any questions that block the plan.
```

---

## PHASE 2 — Project scaffold + Docker

```
Scaffold the project exactly as defined in CLAUDE.md:
- Django project `config` with settings split into base/dev/prod, all secrets from environment variables (django-environ).
- Docker Compose with services: web (gunicorn), db (postgres:16, not exposed to host), redis, celery worker, and mailpit for dev email.
- Dockerfile: multi-stage, python slim, non-root user, pinned versions, healthcheck.
- requirements split (base/dev/prod) with pinned versions.
- .env.example (fake values only), .gitignore (env, media, dumps, staticfiles, pycache), .dockerignore.
- pre-commit with ruff, black, bandit, detect-secrets.
- pytest-django configured, a GitHub Actions workflow running ruff, bandit, pip-audit, pytest and `check --deploy`.
Create the apps listed in CLAUDE.md as empty apps. Make `docker compose up --build` work, and show me how to verify it.
```

---

## PHASE 3 — Security foundation

```
Implement the security foundation from CLAUDE.md rules 3–10 and 14:
- Argon2 hashing, password validators, session settings, secure cookies, HSTS, SSL redirect (prod only), CSP via django-csp with nonces, Permissions-Policy, Referrer-Policy.
- Custom User model (email login) in `accounts`, created BEFORE the first migration.
- Mandatory TOTP 2FA for all staff (django-otp / django-two-factor-auth), backup codes, and force 2FA setup on first login.
- django-axes lockout and rate limiting (django-ratelimit) for login and every public form.
- Admin served at an env-configurable obscure URL; default /admin/ returns 404.
- Reusable encrypted model field (Fernet via `cryptography`, MultiFernet for key rotation, key from env) with tests.
- `audit` app: append-only AuditLog (actor, action, object, IP, timestamp) via signals + admin view/export hooks. Staff cannot edit or delete log rows.
- Cloudflare Turnstile + honeypot helper for public forms (site key/secret from env).
- Generic 404/500 pages, logging with PII scrubbing.
Write tests proving: default admin URL is hidden, staff without 2FA cannot reach admin, encryption round-trips, audit rows are created, lockout triggers.
Run `python manage.py check --deploy` with prod settings and fix every warning.
```

---

## PHASE 4 — Roles and permissions

```
Implement the roles in CLAUDE.md as Django Groups created by a data migration (idempotent).
- Founder = main administrator. Secretary Evaline Mullai and departmental heads are created later through the admin, not hardcoded.
- Branch Coordinators only see data for their own branch (add a `branch` FK on their profile and enforce it in every ModelAdmin get_queryset, has_change_permission and has_view_permission).
- Finance sees only giving data; Media sees only media/resources/news; etc.
- Sensitive data (prayer requests, volunteer details) hidden from roles that do not need it.
Write a permission test matrix (role × model × action) with pytest parametrize. Show me the matrix result.
```

---

## PHASE 5 — Content apps (Plan mode first)

```
Build the content apps with admin management (use django-unfold or similar admin theme in black/flame-orange; ask me before adding it):
- branches: Branch (name, country, city, description, photos, contact fields, activities, is_active). Juba and Yei seeded through a fixture WITHOUT contact details. Adding a new country/branch must need no code.
- programs: Program (title, slug, summary, body, icon, image, category, order). Seed the 5 described programmes + the other core activities from the brief.
- leadership: Leader (name, title, bio, photo, department, order, is_published) + Department. Founder: Justine Malish Michael. Mark all other officers as "to be confirmed by leadership"; they are only published when an admin marks them published.
- events: Event (title, slug, description, programme, branch, start/end, venue, registration_open, capacity, poster). Upcoming vs past logic.
- media_library: Album + Photo + Video (YouTube URL), reports (PDF), testimonies. Safe upload pipeline per CLAUDE.md rule 8.
- resources: sermons, devotionals, study materials (audio/video/PDF/text), categories, series, search.
- news: Post (announcements, reports, testimonies) with draft/published/scheduled.
- core: SiteSettings singleton (ministry name, tagline, logo, social links, contacts, colours, footer text, analytics ID) editable in admin.
All with SEO fields and sitemap entries. Add tests.
```

---

## PHASE 6 — Forms and registrations (Plan mode first)

```
Build the six forms from section 6 of the brief, all following CLAUDE.md rule 7:
1. Volunteer registration (full name, country/location, phone, email, church affiliation, interests/skills, previous ministry experience, testimony, availability).
2. Event registration (linked to an Event, capacity check, duplicate prevention, confirmation email).
3. Prayer request (optional name/contact, request text, "keep confidential" toggle; request text ENCRYPTED).
4. Contact form.
5. Newsletter subscription (double opt-in, unsubscribe link, no purchased lists).
6. Partnership enquiry.
Requirements:
- HTMX progressive enhancement, works without JS, accessible, mobile-first.
- PII fields encrypted; each form shows a short consent/privacy line linked to the privacy policy.
- On submit: save, then Celery task emails the ministry address (configured in SiteSettings, not hardcoded) with NO sensitive body text in the email — only "new submission, view in admin" plus a link — and sends an acknowledgement to the submitter where an email was given.
- Admin: list/filter/search/mark-as-handled, CSV export that is permission-gated and audit-logged, retention setting (auto-purge after N months for prayer requests/contact).
- Rate limit + Turnstile + honeypot on every form.
Write tests for validation, throttling, encryption-at-rest (check raw DB value is not plaintext) and permissions.
```

---

## PHASE 7 — Giving and partnership (Plan mode first)

```
Build the `giving` app. The official donation account and payment gateway DO NOT EXIST YET, so design for that:
- GivingSettings singleton in admin (Founder/Finance only): bank transfer instructions (account name, bank, account number, SWIFT, currency) rendered on the Partner With Us and Give pages. Nothing hardcoded or in fixtures.
- Giving categories as a model (general support, youth revival conferences, evangelism and missions, discipleship, equipment and facilities, youth and leadership development), editable in admin.
- A payment-provider abstraction (`PaymentProvider` interface) with: a ManualBankTransfer provider (works now: donor submits a "I have given" pledge form with reference + category; Finance confirms it in admin) and an empty, documented skeleton for a hosted-checkout gateway (card + mobile money) to plug in later. List 3 candidate gateways that support South Sudan/international donors and what to verify about each.
- Donation model: amount, currency, category, donor info (encrypted), status, provider reference, receipt number. Webhook endpoint skeleton with signature verification and idempotency.
- Partnership page + partnership enquiry (individual, church, organization) and a "current needs" block editable in admin.
- Receipts: PDF or email acknowledgement.
- NEVER store card data. Add tests, including a test that proves no card fields exist in any model.
```

---

## PHASE 8 — Frontend, branding, UX

```
Build the public frontend with Django templates + Tailwind (standalone CLI) + HTMX. Pages: Home, About, Leadership, Programs, Branches (+ detail pages), Events (+ detail + register), Media & Gallery, Sermons & Resources, News, Get Involved, Partner With Us, Give, Prayer Requests, Contact, Privacy Policy, Terms, 404/500.
Design:
- Use EXACTLY the brand palette tokens defined in CLAUDE.md (sampled from the official logo) as Tailwind theme colours + CSS variables: black #0A0A0A, flame #F0652A, deep red #EE362C, amber #F3A831, gold #F8C124 and the flame gradient. Use the logo files from static/brand/ (logo-transparent.png on light, logo-on-dark.png on dark); generate WebP/SVG-ready sizes and a favicon + apple-touch-icon set from them. Dark hero/footer sections with the flame gradient as accent; follow the contrast rule in CLAUDE.md. Strong typography, generous whitespace, authentic revival/restoration feel; Acts 15:16 shown tastefully in the hero or footer.
- Home: hero with tagline, vision, featured programmes, upcoming events, latest news, Give / Volunteer / Register buttons clearly visible.
- Sticky mobile-friendly nav, floating WhatsApp contact button (number from SiteSettings).
- YouTube embeds use youtube-nocookie.com with lazy loading (facade pattern) and CSP frame-src allowance.
- Social icons from SiteSettings (Facebook, Instagram, TikTok, YouTube).
- Performance for slow connections: responsive WebP images with srcset, lazy loading, compressed CSS, no heavy JS, cache headers, `font-display: swap` with self-hosted fonts.
- SEO: meta tags, Open Graph, JSON-LD (Organization), sitemap.xml, robots.txt, canonical URLs.
- Privacy-friendly analytics (self-hosted Plausible or Umami) loaded only per SiteSettings and cookie-consent rules.
- Accessibility WCAG AA.
Use placeholder images where real photos are missing; mark them clearly. Run Lighthouse (or equivalent) and report scores.
```

---

## PHASE 9 — Security audit pass

```
Act as a security reviewer. Audit the entire codebase against CLAUDE.md and the OWASP Top 10 / ASVS Level 2:
- Auth, session, 2FA bypass paths, IDOR on every view/admin action, mass assignment, CSRF, XSS (search for |safe, mark_safe, innerHTML), SQL injection (raw/extra), SSRF (any URL fetching), file upload abuse, open redirects, clickjacking, email header injection, rate-limit gaps, information leakage in errors/logs/emails, insecure defaults in Docker/compose.
- Run: bandit, pip-audit, ruff, `check --deploy`, detect-secrets, and (if installable) trivy on the Docker image.
Produce docs/SECURITY_AUDIT.md with findings ranked by severity, then FIX everything High/Medium and add regression tests. List what remains and why.
```

---

## PHASE 10 — Tests, seed data, docs

```
1. Raise test coverage: permission matrix, all forms, encryption, giving flows, events capacity. Report coverage.
2. Create `manage.py seed_demo` that loads fake demo content (clearly fake names, no real personal data) for local development only; refuse to run when DEBUG=False.
3. Write docs: README (setup), docs/ADMIN_GUIDE.md (plain-language, step-by-step with headings for Secretary / Media / Finance / Branch Coordinators), docs/DEPLOYMENT.md, docs/BACKUP_RESTORE.md, docs/INCIDENT_RESPONSE.md (what to do if an admin account or the server is compromised).
```

---

## PHASE 11 — Production deployment (Plan mode first)

```
Prepare production deployment on a single VPS owned by the ministry (the ministry must own domain, hosting account, database and admin credentials):
- docker-compose.prod.yml: caddy (automatic HTTPS), web, db, redis, celery; only caddy publishes 80/443; internal network for the rest; resource limits; healthchecks; restart policies; log rotation.
- Hardening checklist script/doc for the server: non-root deploy user, SSH keys only, disable password login, ufw (22/80/443), fail2ban, unattended security upgrades, Cloudflare in front (proxy + Turnstile + WAF rules).
- Encrypted nightly backups of Postgres + media (age or restic) to off-site storage, 30-day retention, and a tested restore procedure script.
- Secrets handling: env file with 600 perms on the server, never in git; rotate-key instructions for the Fernet key and Django SECRET_KEY.
- Zero-downtime-ish deploy script (build, migrate, collectstatic, healthcheck, rollback).
- Uptime monitoring + error reporting (PII-scrubbed).
- Email: configure transactional email via the ministry domain with SPF, DKIM and DMARC records documented.
Give me the exact step-by-step commands for the first deployment and the DNS records needed.
```

---

## PHASE 12 — Final handover

```
Prepare the handover package for the ministry: checklist for transferring ownership (domain registrar, hosting, Cloudflare, email, repo, backups storage), admin account creation for the Founder with 2FA, a 1-page "do and don't" security sheet for staff (strong passwords, never share logins, lock screens, phishing awareness), and a launch checklist (privacy policy reviewed, real logo/photos/social links added, officers confirmed by leadership, giving settings entered by Finance, test every form, test restore from backup).
```

---

## Handy prompts for any time

- **Review before commit:** `Review the staged diff for security issues, secrets, and missing tests. Do not commit until I approve.`
- **Fix failing checks:** `Run the full test suite and linters, fix every failure at the root cause (do not skip or weaken tests), and summarize.`
- **Stuck/uncertain:** `Stop. Explain what you are about to change and why, and list alternatives, before editing any file.`
