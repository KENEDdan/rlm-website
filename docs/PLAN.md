# RLM Website: Build Plan

> Binding rules live in `CLAUDE.md`. Decisions made while building are logged in `docs/DECISIONS.md`.
> The original brief (`docs/RLM_website_details.docx`) was **not present** in the repository when this plan
> was written. All ministry copy is therefore placeholder text and fully editable in the admin
> (see DECISIONS D-001).

## 1. Apps and models

All models inherit `core.models.TimeStampedModel` (`created_at`, `updated_at`).
User-facing content also inherits `core.models.PublishableModel` (`is_published`, `slug`, `seo_title`,
`seo_description`). 🔒 = encrypted at rest (Fernet / MultiFernet, `core.fields`). `#` = HMAC blind index
(used for lookups and duplicate detection without decrypting).

| App | Models | Notes |
|---|---|---|
| core | `SiteSettings` (singleton): ministry name, tagline, scripture ref + text, vision, mission, about text, logo, ministry notification email, public email/phone, WhatsApp number, address, footer text, analytics provider/domain/script URL, retention periods (days) per data type. `SocialLink` (platform, url, order). `Page` (privacy, terms; title, body) | SiteSettings: Founder only. SocialLink: Media. |
| accounts | `User` (email login, full name, staff flags, `branch` FK, `department` FK) | TOTP devices + static backup codes come from django-otp. |
| branches | `Country` (name, ISO code), `Branch` (country, name, city, description, activities, meeting times, contact email/phone/address, image, order) | Juba + Yei seeded **without** contacts. A new country or branch is just a new row. |
| programs | `ActivityCategory`, `Activity` (title, summary, body, icon, image, schedule, branches, department, order, CTA) | 4 categories, 13 activities seeded (D-035). Replaced `Program`. |
| leadership | `Department`, `Leader` (name, role title, department, branch, bio, photo, order, `confirmation_status`) | Founder seeded + published; all other posts seeded unpublished, "To be confirmed by leadership". |
| events | `Event` (title, summary, description, program, branch, department, start/end, venue, registration_open, deadline, capacity, poster) | upcoming/past managers, `spots_left`, `can_register`. |
| registrations | `VolunteerApplication` (🔒 full name, email#, phone, church affiliation, skills, experience, testimony, notes; country, location, branch, interests, availability, consent, status). `EventRegistration` (event, 🔒 name, email#, phone, notes; attendees, status; unique(event, email_hash)) | |
| prayer | `PrayerRequest` (🔒 name, email#, phone, request text; keep_confidential, status) | Secretary + Founder only. |
| contact | `ContactMessage` (🔒 name, email#, phone, message; subject, status) | |
| newsletter | `Subscriber` (🔒 email, name; email# unique; status pending/confirmed/unsubscribed; timestamps) | Signed tokens for confirm / unsubscribe; nothing stored. |
| media_library | `Album`, `Photo` (sanitised image + WebP renditions), `Video` (YouTube id only), `Report` (PDF), `Testimony` | Upload pipeline in `core.uploads`. |
| resources | `ResourceCategory`, `Series`, `Resource` (kind sermon/devotional/study; speaker, date, scripture, body, YouTube id, audio, PDF) | |
| news | `Post` (kind, summary, body, image, branch, department, status draft/published/scheduled, publish_at, author) | Scheduled posts appear automatically when `publish_at` passes. |
| giving | `GivingSettings` (singleton; bank-transfer + mobile-money instructions, gateway toggle, receipt prefix, partnership intro), `GivingCategory`, `CurrentNeed`, `Donation` (category, amount, currency, provider, status, 🔒 donor name/email#/phone/message/transfer ref, anonymous flag, receipt no., provider ref, idempotency key), `WebhookEvent` (provider, event id unique, payload hash), `PartnershipEnquiry` (type, 🔒 name, organisation, email#, phone, message; country, status) | **No card fields, ever** (test enforced). |
| audit | `AuditLog` (timestamp, actor id + email snapshot, action, app/model, object id, non-PII repr, IP, UA, extra JSON) | Append-only: model guards + Postgres trigger blocking UPDATE/DELETE. |

## 2. URL map

| URL | Page |
|---|---|
| `/` | Home |
| `/about/` | About (vision, mission, Acts 15:16) |
| `/leadership/` | Published leaders |
| `/activities/`, `/activities/category/<slug>/`, `/activities/<slug>/` | Activities (old `/programs/...` redirect) |
| `/branches/`, `/branches/<slug>/` | Branches, grouped by country |
| `/events/`, `/events/past/`, `/events/<slug>/`, `/events/<slug>/register/` | Events + registration |
| `/gallery/`, `/gallery/<slug>/`, `/gallery/videos/`, `/gallery/reports/`, `/testimonies/` | Media & gallery |
| `/resources/`, `/resources/<slug>/` | Sermons & resources (filter + search) |
| `/news/`, `/news/<slug>/` | News |
| `/get-involved/` | Volunteer form |
| `/partner/` | Partner with us + enquiry form + current needs |
| `/give/`, `/give/pledge/`, `/give/thank-you/` | Give (bank instructions from GivingSettings, pledge form) |
| `/prayer/` | Prayer request |
| `/contact/` | Contact |
| `/newsletter/subscribe/`, `/newsletter/confirm/<token>/`, `/newsletter/unsubscribe/<token>/` | Newsletter double opt-in |
| `/privacy/`, `/terms/` | Legal pages (editable) |
| `/sitemap.xml`, `/robots.txt`, `/healthz/` | Infra |
| `/payments/webhook/<provider>/` | Gateway webhooks (signature verified, idempotent) |
| `/<ADMIN_URL>/` | Admin (env-configured; `/admin/` → 404) |
| `/<ADMIN_URL>/account/login/`, `.../2fa/setup/`, `.../2fa/verify/`, `.../logout/` | Staff auth + mandatory TOTP |

## 3. Role / permission matrix

V = view, A = add, C = change, D = delete, X = export (custom permission). "own" = scoped to the user's
branch (Branch Coordinator) or department (Departmental Head) in every admin queryset and object check.

| Model | Founder | Secretary | Finance | Programs & Events | Media & Comms | Branch Coord. | Dept. Head |
|---|---|---|---|---|---|---|---|
| User, Group | VACD | – | – | – | – | – | – |
| SiteSettings, Page | VC | – | – | – | – | – | – |
| SocialLink | VACD | – | – | – | VACD | – | – |
| PageText (headings/wording) | VC | – | – | – | VC | – | – |
| FormOption (form choice lists) | VAC | VAC | – | – | – | – | – |
| AuditLog | V | – | – | – | – | – | – |
| Country, Branch | VACD | V | – | V | V | VC own | V |
| Program | VACD | V | – | VACD | V | V | VC own |
| Department, Leader | VACD | VAC | – | – | VAC | – | – |
| Event | VACD | VACD | – | VACD | V | VAC own | VAC own |
| EventRegistration | VCDX | VCX | – | VCX | – | VC own | V own |
| VolunteerApplication | VCDX | VCDX | – | – | – | VC own | – |
| PrayerRequest | VCDX | VCDX | – | – | – | – | – |
| ContactMessage | VCDX | VCDX | – | – | – | – | – |
| Subscriber | VCDX | VCX | – | – | VX | – | – |
| Album/Photo/Video/Report/Testimony | VACD | V | – | – | VACD | VAC own (albums) | – |
| ResourceCategory/Series/Resource | VACD | – | – | – | VACD | – | – |
| Post (news) | VACD | VACD | – | – | VACD | VAC own | VAC own |
| GivingSettings | VC | – | VC | – | – | – | – |
| GivingCategory, CurrentNeed | VACD | – | VACD | – | – | – | – |
| Donation, PartnershipEnquiry | VCDX | – | VCDX | – | – | – | – |
| WebhookEvent | V | – | V | – | – | – | – |

Founder = superuser (and member of the Founder group for clarity). Groups are created by an idempotent data
migration; the matrix is asserted by `tests/test_permission_matrix.py`.

## 4. Threat model

| Asset | Threat | Mitigation |
|---|---|---|
| Admin accounts | Credential stuffing, brute force, phishing | Obscure admin URL, django-axes lockout, IP rate limit, Argon2, 12+ char validators, **mandatory TOTP** + backup codes, short sessions, audit of logins |
| Prayer requests, volunteer PII, donor data | DB dump / backup theft | Field-level Fernet encryption with rotation, encrypted off-site backups, DB never exposed |
| Same | Insider over-reach / IDOR | Groups with least privilege, branch/department scoping in every queryset + object permission, audit of views/exports |
| Same | Leakage via email / logs / errors | Notification emails contain no submission content; PII scrubbing filter + Sentry `before_send`; generic error pages; `DEBUG=False` |
| Public forms | Spam, bots, flooding | Turnstile, honeypot, per-IP rate limits, size limits |
| Site visitors | XSS, clickjacking, injection | Auto-escaping, no `|safe` on user input, strict CSP with nonces, `X-Frame-Options: DENY`, ORM only |
| Uploads | Malicious files, polyglots, EXIF location leak | Extension + libmagic check, size caps, random names, Pillow re-encode (strips EXIF/GPS), PDF header check; no public-form uploads at all |
| Giving | Fake confirmations, card data exposure, replayed webhooks | No card data stored (hosted checkout only), Finance confirms manual pledges, HMAC-verified webhooks with event-id idempotency |
| Infrastructure | Exposed services, container breakout, lost server | Only Caddy public, non-root read-only containers, pinned images, ufw/fail2ban, tested restores |
| Supply chain | Malicious/vulnerable dependency | Hash-pinned requirements, pip-audit + bandit in CI, Dependabot |

## 5. Unknowns, all configurable

| Unknown | Where it's configured |
|---|---|
| Logo variants | `SiteSettings.logo` (falls back to `static/brand`) |
| Domain | `DJANGO_ALLOWED_HOSTS`, `SITE_URL`, `Caddyfile` env |
| Social links | `SocialLink` rows (admin) |
| Contacts, WhatsApp | `SiteSettings` (admin) |
| Payment gateway | `GivingSettings.gateway_*` + `giving/providers/` skeleton |
| Bank details | `GivingSettings` (Founder/Finance in admin) |
| Officers | `Leader` rows, unpublished until confirmed |
| Analytics | `SiteSettings.analytics_*` (only loaded after consent) |

## 6. Build order

A plan → B scaffold → C security foundation → D roles → E content apps → F forms → G giving →
H frontend → I security audit → J tests + docs → K production. Each phase ends with tests, linters and a commit.
