# Security audit, re-run 3: website requirements update (activities, Vision/Mission, hero, Technical Team, uploads)

Date: 2026-11-22. Scope: everything changed for the November 2026 website requirements (docs/DECISIONS.md
D-034 to D-038): the central upload policy, the settings split and Technical Team role, the bank-detail change
flow, enquiry routing, content versioning and rollback, the Vision/Mission approval flow, hero backgrounds
(including video), and the activities that replaced the programmes. Earlier audits (below) still apply.

## R3.1 Summary

| Severity | Found | Fixed | Accepted |
|---|---|---|---|
| High | 0 | 0 | 0 |
| Medium | 2 | 2 | 0 |
| Low | 4 | 4 | 0 |

No Critical or High issue. Bandit: 0 issues (35,172 lines). pip-audit: no known vulnerabilities (no package
was added). ruff and black clean. `manage.py check` clean; `makemigrations --check` clean.
Tests: full suite 3,345 passed (fresh test database), plus 10 refusal-path tests added afterwards
(`tests/test_approval_rules.py`, passing). Coverage of the new security code: upload policy 89 %, uploads 94 %,
private files 87 %, versioning 85 %, Vision/Mission approvals 97 %, bank-detail flow 99 %, hero 97 %, portal access
97 %, roles 96 %; core + giving + accounts + portal + programs + contact together 93 %.

## R3.2 Method

* Code review of every new view, service and template against CLAUDE.md rules 2-15, focusing on access control
  (who reaches each URL, admin page and queryset), re-authentication, segregation of duties, output escaping and
  the CSP, and on upload parsing (malformed input must be refused, never crash or over-read).
* Tests for each boundary (tests/test_technical_team.py, test_vision_mission.py, test_hero.py,
  test_activities.py, test_upload_policies.py), including hand-built malicious files: wrong extension, renamed
  executable, JPEG/HTML polyglot, oversized file, pixel bombs (49 MP and 100 MP), SVG with script (by name and
  disguised as PNG), HTML disguised as PDF, macro documents (.docm, .xlsm, and a .docx carrying vbaProject.bin),
  embedded OLE objects, a 60 MB zip bomb, PDFs with JavaScript (plain, `#xx`-obfuscated and inside a compressed
  object stream), encrypted PDF, double extensions, path traversal, NUL and right-to-left-override names,
  long/non-H.264/audio-carrying/4K videos, UTF-16 CSV, ClamAV infected/unreachable.
* Tools: bandit, pip-audit, ruff, Django system checks, full test suite.

## R3.3 Findings fixed

### M-1 Bank details could be changed by any single Finance user, silently (Medium, rules 2, 5, 6)
Before: the Finance group could edit the account number in the admin with no second person, no alert and no
history beyond the generic audit row. Fix: `giving.BankDetailChange` two-person flow (D-034) with
re-authentication at both steps, masked email alerts, append-only history (previous details kept encrypted),
"Last verified" date for donors; `GivingSettings.save()` refuses any other change and the admin no longer renders
the fields. Test: `test_bank_change_needs_reauth_second_person_and_alerts`, `test_no_other_role_can_read_or_edit_bank_details`.

### M-2 Finance enquiries reached the general inbox and Membership (Medium, rule 5)
Before: every contact message, including giving and partnership questions, went to the general notification
address and was visible to Membership in the admin. Fix: subject selector, finance-queue routing in the admin
queryset and a Finance-only portal screen; alerts for finance-related submissions go only to the Finance heads.
Test: `test_finance_enquiries_go_only_to_the_finance_queue`.

### Lows fixed
* **L-1 Singleton admin pages redirected before checking permission:** a user without access to Site settings or
  Giving settings got a redirect to the change page (then a 403), confirming the row exists. Now 403 first.
* **L-2 Privacy facts read retention from the wrong settings object** after the split, so the privacy page would
  have listed "kept" for every type (rule 13 accuracy). Fixed and covered by the existing privacy tests.
* **L-3 CSV formula neutralisation missed cells with leading spaces** (`"  =cmd"`). Now stripped before the check.
* **L-4 Upload validation opened stored files during form validation** (an unreadable or missing file raised a
  500). Stored files are now trusted as validated at upload time; only new uploads are checked.

## R3.4 Accepted risks and decisions for the ministry

* **ClamAV is off by default** (needs ~1.5 GB RAM). All other upload checks run regardless; re-encoding destroys
  image payloads and executables are refused by content. Enabling it is one env flag plus a compose profile, and
  it fails closed. **Confirm** whether to run it on the server.
* **External links are not fetched** by the broken-link check (no outbound requests from the server, no SSRF
  surface); only their form (`https://`) is checked.
* **The video parser is in-house** (MP4 boxes, WebM EBML) to avoid adding ffmpeg to the image. It only reads
  container headers and is bounded by the 15 MB cap; malformed files are refused. Browsers then decode the file in
  their own sandbox; videos are served from our origin with `nosniff` and the `/uploads/` sandbox CSP.
* **Vision/Mission approvers** are the Super Admin or a current `finance.Approver` row with role Founder or
  Executive Director; acting approvers are not included (they cover expenditure only). **Confirm.**
* **Who may open the bank-detail screens:** Finance head, Founder/Executive Director, Super Admin. Ordinary
  Finance members cannot. **Confirm.**

## R3.5 Areas reviewed and found sound

| Area | Evidence |
|---|---|
| Technical Team boundary | Role matrix + `TECHNICAL_FORBIDDEN_*` asserted; admin and portal URLs of finance, giving, donors, members, prayer, discipleship, registrations, contacts, accounts, audit, system settings and upload limits return 403/404 for the role (parametrised tests). |
| Separation of duties | Vision/Mission: author never approves; approval needs password + 2FA. Bank details: proposer never confirms; both steps re-authenticate; one pending change at a time (DB constraint). |
| Versioning | `ContentVersion` and `BankDetailChange` refuse updates and deletes in the model; rollback re-checks the user's change permission on that model and skips fields with their own controlled path (Vision/Mission, Activity.department unless Super Admin). |
| Output / CSP | Hero focal point and overlay are integers rendered into a nonce'd `<style>` (no inline style attributes); button links validated on save and re-checked at render; `media-src 'self'`; the hero editor preview uses `data:` URLs (already allowed for images) and CSSOM only; previews are `noindex` and staff-only. |
| Uploads (rule 8) | One policy per field, enforced in forms and before storage; enumeration test; `accept` is a hint only; public forms have no file inputs (tested); request bodies capped in Caddy and Django; private files outside the web root, served only through the permission-checked, audit-logged download view as attachments with generated names. |
| Activities | Public queries return only published activities in published categories; department routing editable only by the Super Admin; dashboard counts respect per-assignment branch scope (tested). |

---

# Security audit, re-run 2: staff portal, departments and the account system

**Date:** 2026-11-19 · **Scope:** everything added since the Phase I audit below: the `portal` app, the seven
department apps (`membership`, `finance`, `logistics`, `missions`, `discipleship`, `communications`,
`development`), the four questionnaire forms, private uploads, and the rebuilt account and role system
(`accounts.services`, `guard`, `integrity`, invitations, re-authentication). **Standard:** CLAUDE.md rules 1-15,
OWASP Top 10 (2021), OWASP ASVS 4.0 Level 2 (V1 architecture, V2 authentication, V3 sessions, V4 access
control, V7 logging, V8 data protection, V12 files). Threat model: `docs/THREAT_MODEL.md`.

## R2.1 Summary

| Severity | Found | Fixed | Remaining |
|---|---|---|---|
| Critical | 0 | – | – |
| High | 1 | 1 | 0 |
| Medium | 4 | 4 | 0 |
| Low | 5 | 3 | 2 accepted (R2.4) |

After the fixes: **2,342 tests pass** (148 in the new test files), **94% line coverage overall**; the security
modules are at 90-100% (`accounts/guard.py` 96%, `accounts/integrity.py` 100%, `accounts/services.py` 90%,
`portal/access.py` 95%, `portal/resources.py` 86%; `accounts/tasks.py` raised from 0% to covered).

## R2.2 Method and tool results

* Manual review of every new view, form, resource definition, service, signal and template, with the question
  "can a user reach a record outside their department, branch, head level or the minors/pastoral rules?".
* A **portal-wide smoke test** that loads the demo data and opens every dashboard, printable report, budget
  page and every resource's list/detail/edit screen as the Super Admin; a test that **every** registered
  screen refuses staff without a role in that department (list and CSV export); a test that walks **every URL
  pattern** anonymously with GET and POST of account-like data and proves no user is created.
* A visual check through the real sign-in (password + TOTP) in headless Chromium, desktop and 390 px phone.

| Tool | Result |
|---|---|
| `ruff check .` / `black --check .` | clean |
| `bandit -c pyproject.toml -r .` (CI configuration) | **0 issues** (one deterministic demo-data RNG marked `nosec B311`) |
| `pip-audit -r requirements/base.txt --require-hashes` | no known vulnerabilities (**no new packages were added**) |
| `manage.py check --deploy` (prod settings) | only `rlm.E001` (Turnstile keys absent in the local `.env`, as designed) |
| `makemigrations --check` | no changes |
| Grep for `\|safe`, `mark_safe`, `csrf_exempt`, `.raw(`, `.extra(`, `RawSQL`, cursors, inline `<script>`, `style="`, `on*=` handlers in new code | none |

## R2.3 Findings fixed

### H-1 Private uploads could not be stored in the containers (High: availability of financial records; rule 8)
The private storage resolved its location at import time and `/app/data/private` did not exist (or was not
writable by the app user) in the images, so receipts, vouchers, permits, contracts and member documents would
have failed to upload in production. **Fix:** `PrivateStorage` reads `PRIVATE_MEDIA_ROOT` on use and refuses to
build a public URL; the Dockerfile creates the folder; both compose files mount a separate `private` volume
that **Caddy never mounts**; `media-init` fixes its ownership; nightly backups add an encrypted
`-private.tgz.age` archive and `restore.sh private` restores it. Test: `test_private_file_upload_download_is_scoped_and_audited`.

### M-1 Group changes were not audited (Medium, rule 6)
The `m2m_changed` handlers for `User.groups` and `User.user_permissions` were connected with weak references
to closures and were garbage-collected, so role-group changes (inside or outside the portal) left no audit
entry. **Fix:** `weak=False`. Tests: `test_role_change_audited_with_old_and_new_values`,
`test_out_of_band_group_and_membership_changes_detected`.

### M-2 The Django admin could manage users without the portal's safeguards (Medium, rules 4-5)
Superusers could add/edit users and set passwords in the admin, bypassing re-authentication, invite-only
onboarding, the Super Admin limit and last-Super-Admin protection. **Fix:** the admin's user screens are
read-only for everyone; the "set another user's password" screen was removed. Test:
`test_user_admin_is_read_only_even_for_superusers` and the per-role admin checks.

### M-3 The Founder group carried account-administration permissions (Medium, rule 5)
A non-superuser placed in the Founder group would have had `accounts.*` and `auth.*` permissions. **Fix:**
`founder_permissions()` excludes account, group, permission, OTP, axes, session and department-membership
permissions; account management depends on the superuser flag alone, enforced in `accounts.services`. Test:
`test_founder_group_has_content_permissions_but_not_account_admin`.

### M-4 The documented emergency procedure bypassed the account guard (Medium, rules 4 and 6)
`INCIDENT_RESPONSE.md` told the technical lead to disable a compromised Founder with a raw
`QuerySet.update()` in a shell: no audit entry, no alert, sessions left alive. **Fix:**
`manage.py emergency_disable --email … [--reset-2fa]` can only remove access, ends sessions, is audited and
alerts the Super Admins; the guide was rewritten. Test: `test_emergency_disable_command`.

### Lows fixed
* **L-1** Department workflow URLs (`…/<pk>/<step>/`) shadowed the generic `…/<pk>/edit/` routes, which would
  have bypassed the generic per-object edit check for those screens. All steps now live under `/step/`, and
  `test_workflow_urls_never_shadow_generic_resource_routes` guards every registered screen.
* **L-2** Charts were unreadable on phones and wide tables made dashboards scroll sideways (WCAG 1.4.10
  reflow). Fixed; verified at 390 px.
* **L-3** `monthly_series` crashed for models with a field called `month` (dashboard denial of service).
  Fixed with a private annotation name.

## R2.4 Accepted risks and decisions for the ministry
* **Shell or database access cannot be prevented by the application.** Changes made there are *detected*
  (model guard: immediate alert; HMAC fingerprint check every 15 minutes, keyed with `SECRET_KEY`, which is
  not in the database) but not blocked. Someone with both the database and `SECRET_KEY` could forge the
  fingerprint: protect the server (DEPLOYMENT.md).
* **Invitation tokens are in the link path**, so they can appear in reverse-proxy access logs. They are
  single-use, expire after 48 hours, only their SHA-256 is stored, and the acceptance page loads no
  third-party resources (no Referer leak). Keep access logs private and short-lived.
* Executive Leadership sees **aggregate** finance figures (income, expenditure, cash, pledges) for the whole
  ministry. Confirm this is intended (open question in the final report).
* Branch Coordinator status restricts **every** department the person belongs to (simplest safe rule).
* Ages and dates of birth are self-declared; the minors rule depends on them. Staff should correct a record
  when they learn the real age.
* "Printable / PDF" relies on the browser's Save as PDF; no server-side PDF library was added.

## R2.5 Areas reviewed and found sound
Department scoping on every list, detail, form, delete, file download and CSV export (one code path,
`Resource.get_queryset` + `Resource.can`, out-of-scope objects are 404); dropdown choices limited to visible
records (unknown related models get none); post-save scope re-check; requester-department sharing (purchase
and design requests) limited to the requester's own department and to view/add; minors visible only to the
Membership/Discipleship head and Founder; pastoral notes limited to the assigned mentor, head and Founder,
never exportable, every view audited; Finance ledger segregation of duties, Founder approval above the
threshold, posted entries immutable at model, queryset and view level; procurement approver never the
requester; head-only exports, all audit-logged and CSV-injection safe; private files outside the web root
with permission-checked, audited, `no-store` downloads and libmagic content checks; invite-only onboarding
with forced TOTP enrolment; re-authentication for account changes; last-Super-Admin protection; session
termination on deactivation; dormant-account handling; questionnaire forms with CSRF, honeypot, Turnstile,
rate limiting, consent text and encrypted sensitive fields; staff-alert emails without personal data.

---

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
