# Security audit: Phase I

**Date:** 2026-11-16 · **Scope:** whole repository at the end of phases A–H · **Standard:** CLAUDE.md
security rules 1–15, OWASP Top 10 (2021), OWASP ASVS 4.0 Level 2.

## 1. Summary

| Severity | Found | Fixed | Remaining |
|---|---|---|---|
| Critical | 0 | – | – |
| High | 0 | – | – |
| Medium | 5 | 5 | 0 |
| Low | 11 | 4 | 7 (accepted or scheduled for phase K, see §4) |

No High or Critical issues were found. Every Medium was fixed and has a regression test in
`tests/test_security_audit.py`. After the fixes: **1105 tests pass, 94% coverage**.

## 2. Method and tool results

Manual review of every view, form, admin class, middleware, settings file, task, template tag, the upload
pipeline, the payment code, the Dockerfile, compose file and CI, plus automated scans:

| Tool | Result |
|---|---|
| `ruff check .` / `black --check .` | clean |
| `bandit -r . -c pyproject.toml` | **0 issues** (3 Medium were false positives with a misplaced `# nosec`; fixed) |
| `pip-audit -r requirements/base.txt` | no known vulnerabilities |
| `manage.py check --deploy` (prod settings) | clean with Turnstile keys set; **new check `rlm.E001`** fires without them |
| `detect-secrets` | 3 hits, all test fixtures (marked `allowlist secret`) |
| Template/JS grep for `\|safe`, `autoescape off`, `innerHTML`, `eval`, `document.write` | none (only plain-text email templates use `autoescape off`) |
| Grep for `.raw(`, `.extra(`, `RawSQL`, cursors | one constant `SELECT 1` in `/healthz/` |
| Outbound HTTP (SSRF) | only the constant Turnstile URL |
| **Trivy 0.58.2** on the production image | Python packages: 12 Medium/Low, **all in pip** → pip removed from the runtime image → **0**. Debian OS packages: 0 fixable High/Critical; unfixed ones listed in §4 |

## 3. Findings fixed

### M-1 Turnstile silently fails open in production (Medium, rule 7)
`TURNSTILE_ENABLED` defaulted to "is a secret key set?". A production server deployed without the key ran
every public form with **no bot protection** and no warning.
**Fix:** production enables Turnstile by default; `verify_turnstile` rejects when it is enabled without a
secret (fail closed, no network call); new deploy check `rlm.E001` (keys missing) / `rlm.W001` (disabled
on purpose). CI passes placeholder keys to `check --deploy`.
*Files:* `core/turnstile.py`, `core/checks.py`, `config/settings/prod.py`, `.github/workflows/ci.yml`.

### M-2 Payment webhook could lose a status update (Medium, rule 11 "idempotent payment handling")
The event row was committed *before* the donation was updated. If the update failed, the gateway's retry
was answered "duplicate" and the gift stayed unconfirmed forever.
**Fix:** record + apply in one transaction (a failure stores nothing, so the retry is processed); events
left unprocessed by older code are re-applied.
*Files:* `giving/views.py`, `giving/services.py`.

### M-3 Encryption key rotation was documented but missing (Medium, rule 3)
`core/crypto.py` told operators to run `manage.py rotate_encryption_keys`, which did not exist.
**Fix:** command added. It re-encrypts every encrypted column of every model with the primary key, rebuilds
blind indexes (so `BLIND_INDEX_KEY` can rotate too), supports `--dry-run`, runs in one transaction,
**aborts without writing if any row cannot be decrypted**, keeps `updated_at` untouched and writes an audit
entry. *File:* `core/management/commands/rotate_encryption_keys.py`.

### M-4 No way to export or erase one person's data (Medium, rule 13)
**Fix:** `core/privacy.py` finds every record for an email through the blind indexes (all 7 models that
store a person's email). `manage.py personal_data find|export|erase --email …`:
* export: decrypted JSON of everything held (keyed hashes omitted);
* erase: deletes submissions, **anonymises donations** (amount/date/receipt kept for the accounts, donor
  name/email/phone/message/reference cleared); needs `--yes`;
* both are audit-logged **without** the email address.

### M-5 Admin list pages of sensitive data were not audited (Medium, rule 6)
Opening one prayer request/volunteer/donation was logged, but the list pages (which show names) were not.
**Fix:** for every admin with `audit_views = True`, each list view is logged as `view` with
`{"list": true, "shown": n, "query": filters}`. The search box text is **not** stored (it may be an email).
*File:* `core/admin_mixins.py`.

### Lows fixed
| ID | Finding | Fix |
|---|---|---|
| L-1 | Webhook matched donations by reference across providers; a signed event without an amount could confirm a gift | match `provider` too; `confirmed` requires a matching amount |
| L-2 | Images between 40 and 80 MP only raised a Pillow *warning* (memory use) | warning treated as an error in `validate_image_upload` |
| L-3 | If a key were missing, a record read as `[unreadable…]` and saved in admin would overwrite the real ciphertext | `EncryptedTextField` refuses to save the placeholder |
| L-4 | pip (12 CVEs) shipped in the runtime image | uninstalled from venv and system Python in the `prod` stage |

## 4. Remaining items (accepted or scheduled)

| ID | Item | Severity | Why it remains / plan |
|---|---|---|---|
| R-1 | django-otp stores TOTP secrets and backup codes unencrypted in the DB | Low | Library design. An attacker would need DB access **and** the Argon2-hashed password. DB is never exposed; backups are encrypted (phase K). Revisit if django-otp adds encrypted storage. |
| R-2 | First sign-in enrols 2FA for whoever holds the password first | Low | Inherent to self-enrolment. Mitigation in the admin guide (phase J): Founder hands out the first password out-of-band and the user signs in straight away; 2FA enrolment is audit-logged (`2fa_setup`). |
| R-3 | Lockout is per username+IP, so slow password spraying from many IPs is possible | Low | Locking on username alone lets anyone lock staff out. Password alone never grants access (mandatory TOTP). |
| R-4 | Debian base image: unfixed CVEs (e.g. CRITICAL CVE-2025-7458 libsqlite3, CVE-2023-45853 zlib/minizip) | Low | No upstream fix. SQLite is only used during the build step; minizip is not used. Rebuild monthly / on Dependabot alerts; consider a newer base when Python 3.12 slim on Debian 13 is adopted. |
| R-5 | ~~GitHub Actions pinned by tag, images by tag not digest~~ | Low | **Resolved in phase K:** actions pinned to commit SHAs, all images pinned by digest, Dependabot covers both. |
| R-6 | Admin "event" list filter shows titles of unpublished events to scoped staff | Info | Titles only, staff only. |
| R-7 | Donation `finance_notes` are kept when a donor is erased | Info | Staff-written accounting notes; Finance must not put donor identity in them (admin guide). |

## 5. Requirements for phase K (production)

**Status: all five are implemented in `docker-compose.prod.yml` / `docker/Caddyfile` and were verified in
the local production rehearsal (`docs/DEPLOYMENT.md`).** Original requirements:

1. **Client IP:** Caddy must set `X-Real-IP` to the real visitor IP. Behind Cloudflare, use
   `trusted_proxies` with Cloudflare ranges and `CF-Connecting-IP`; otherwise rate limits and lockouts would
   apply to Cloudflare's edge IPs (all visitors share one bucket). `TRUST_PROXY_IP_HEADER` is on in prod.
2. **Media (`/uploads/`)** is served only in DEBUG by Django. Caddy must serve it with
   `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox; default-src 'none'`, no directory
   listing, and never serve anything under `uploads/private/`.
3. Set `GUNICORN_FORWARDED_ALLOW_IPS` to the Caddy container address instead of `*`.
4. Production `.env` must set `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` (deploy check `rlm.E001`).
5. Pin GitHub Actions and container images by digest (R-5).

## 6. Areas reviewed and found sound

| Area (OWASP) | Evidence |
|---|---|
| A01 Access control / IDOR | Role matrix asserted by `tests/test_permission_matrix.py`; branch/department scoping in querysets, object permissions, FK choices and save; user and role admin superuser-only; OTP device admins unregistered; `/admin/` 404, obscure env-configured path. |
| A02 Cryptography | Fernet/MultiFernet per field, separate HMAC key for blind indexes, `__str__` of sensitive models is non-PII (Django's LogEntry stores no names), Celery messages carry only label + pk. |
| A03 Injection / XSS | ORM only; no `\|safe`; plain-text bodies rendered by escaped `paragraphs` filter; JSON-LD escaped like `json_script`; CSV export neutralises formula injection; strict CSP with nonces, HTMX `allowEval:false`, `selfRequestsOnly:true`; email subjects go through Django's header-injection guard. |
| A04 Insecure design | Password never yields a session without TOTP; event capacity uses `select_for_update`; duplicate registrations and newsletter sign-ups give the same response (no enumeration); unsubscribe needs POST. |
| A05 Misconfiguration | `DEBUG=False`, HSTS preload, `__Host-` cookies, `X-Frame-Options: DENY`, COOP, Permissions-Policy, `no-store` on staff pages, generic error pages (500 renders without context). |
| A06 Components | Hash-pinned requirements, pip-audit clean, Trivy run, checksum-verified Tailwind binary. |
| A07 Authentication | Argon2, 12+ chars + complexity, axes lockout, IP rate limit, 2-hour sliding session, expires at browser close, safe `next` redirects, 2FA middleware logs out unverified sessions in the admin area. |
| A08 Integrity | Webhooks: HMAC over raw body with `compare_digest`, 5-minute replay window, size cap, unique event id. |
| A09 Logging | Append-only audit log (model guard + Postgres trigger); PII scrubbing filter on all logs and Sentry `before_send`. |
| A10 SSRF | Only constant Turnstile URL is fetched. |
| Uploads (rule 8) | Extension whitelist + libmagic + Pillow verify, size caps, uuid names, re-encode strips EXIF/GPS, outside web root, no public-form uploads. |
| Containers (rule 10) | Non-root uid 10001, code owned by root (read-only to the app), DB/Redis unpublished, dev ports bound to 127.0.0.1. |
