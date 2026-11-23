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

## D-018: Membership Administration
(2026-11-19) Member numbers (`RLM-000123`) are given on **approval**, so declined applicants never use one.
Admission follows received → under review → approved / not accepted (head only, private reason required,
emailed decision that never repeats what the applicant wrote) → orientation → integration → active, then
inactive or transferred. The **engagement score** is the share of the member's branch's activities in the last
90 days they attended, plus 10 while they hold a current service record (capped at 100). Bulk messages go only
to members who ticked a new, optional "send me ministry announcements" box on the form (needed to respect
opt-in) and never to under-18s; WhatsApp is click-to-chat links (no WhatsApp API, nothing sent automatically).

## D-019: Finance controls
(2026-11-19) Approving an entry **posts** it (one step) and only someone other than the recorder can do it;
above `FinanceSettings.approval_threshold` (placeholder 1,000, editable by the Finance head) only a Super Admin.
Corrections are negative mirror entries that need the same approval. Confirming a website gift issues the
receipt **and** creates an income entry awaiting another person's approval. Budgets are per **calendar year**
(open question: the ministry's financial year). Other departments see only "Our budget" totals; Executive
Leadership sees ministry-wide aggregates on the overview (open question).

## D-020: Procurement
(2026-11-19) Any department files purchase requests in its own name and sees only its own. At least **three**
quotations are required before a recommendation (no override); choosing a supplier that is not the cheapest
needs a written reason. Finance confirms a **current-year budget line of the requesting department**;
approval is by the Logistics head or a Super Admin and never by the requester. The purchase order amount and
supplier come from the recommended quotation.

## D-021: Missions → Discipleship handoff, pastoral care
(2026-11-19) Every `NewConvert` creates a `FollowUp` through a signal (audited as a handoff); first contact is
due 7 days after the decision. Missions sees the follow-up status on its convert records; the Executive
Overview shows the handoff counts. Mentors and facilitators are chosen from Discipleship department members.
Pastoral notes and check-ins: assigned mentor, Discipleship head, Founder; never exportable; only the author
edits a note. Minors in converts, registrations and disciples are visible to the relevant head and the Founder.

## D-022: Media & Communications
(2026-11-19) Testimonies gained "the person is 18 or over"; approval and publication require it and consent.
Existing approved testimonies are **hidden** until Media confirms the box (safe default; nothing is live yet).
Social reach is typed in monthly from each platform's insights (no tracking scripts). Design requests are shared
with the requesting department (view and add only). Albums, videos, testimonies and hero slides are the same
records in the portal and the admin.

## D-023: Development & Infrastructure
(2026-11-19) Project costs are recorded on the project (with the Finance voucher number) rather than read from
the ledger, so Development can work before Finance has posted entries (open question: whether to link them to
ledger entries later). A capital proposal sent to Finance creates a Finance funding proposal (audited handoff).
The project timeline is a server-rendered SVG (planned span, progress from the latest site visit, today line).

## D-024: The four questionnaire forms
(2026-11-19) Wording, sections and button labels follow `docs/membership_policy_questionnaire.md`. Choices:
* "Country and city of residence" is two fields (filtering by country, mobile autocomplete).
* Email is optional on the Membership and Discipleship forms (many people use WhatsApp only) and required on
  the Partnership and Finance-volunteer forms.
* Partnership category, areas and partnership types stay **admin-managed Form options** (D-011); growth areas,
  yes/no answers and gender are fixed codes because reports and assessments depend on them.
* "Which area would you like to grow in?" allows several answers.
* Under 18 (from the date of birth or age): guardian name, contact and consent are required, and the person is
  never put on announcement lists. The **general volunteer form is kept** for serving interests; the Finance &
  Accountability volunteer form is separate because it needs vetting.
* Unsuccessful applications (not accepted / not taken forward) are deleted after
  `SiteSettings.retention_unsuccessful_days` (365). Data-subject export/erase covers the new records; donors
  are anonymised (pledges are financial records).

## D-025: Operations
(2026-11-19) Private uploads live on their own `private` Docker volume (never mounted by Caddy) and are in the
nightly encrypted backups. `manage.py emergency_disable` is the only server-side account command besides the
first-Super-Admin bootstrap: it can only remove access, ends sessions and alerts the Super Admins.
`seed_demo` fills every dashboard with fake data (DEBUG only, no accounts) and `seed_indicators` creates
suggested targets. No new third-party packages were added for any of this work.


## Ministry decisions (Nov 2026)

Recorded verbatim as received on 2026-11-20. These are binding; how each was implemented, and the defaults
chosen where a decision left something open, are in D-026 to D-033 below.

1. EXECUTIVE FINANCE DASHBOARD
- Add an "Executive Leadership" role (Founder/Executive Director plus any members the Super Admin adds). Give it an Executive Finance page showing ministry-wide SUMMARIES only: income received, expenditure, cash balances, outstanding pledges, approved budgets, budget vs actual by department and branch, with the financial-year and month filters.
- Detailed ledger entries, donor identities, vouchers and receipts stay visible only to Finance and the Founder. Executive Leadership gets drill-down to totals and categories, not individual donors or documents unless they also hold the Finance role. Test this boundary.

2. FINANCIAL YEAR
- Financial year = 1 January to 31 December for every branch and department. Create a FinancialYear model (default current year), and make budgets, ledger, indicators, reports and dashboards all period-aware. Prevent posting into a closed year; provide a Super Admin/Finance-head "close year" action (audit-logged, reversible only by Super Admin with re-authentication). Quarters and months derive from the calendar year.

3. APPROVAL RULES
- EVERY expenditure or financial commitment (purchase orders, procurement approvals, project payments, event budgets, mission trip budgets, reimbursements) requires Founder/Executive Director approval before it can be paid or committed. Remove any lower approval thresholds; keep segregation of duties (requester cannot approve own request, recorder cannot approve).
- Unbudgeted expenditure (no matching approved budget line, or exceeding the remaining line balance) is flagged "UNBUDGETED" and requires a second step: executive approval with a mandatory written justification and, if configured, a budget reallocation or supplementary budget. Show these prominently on Finance and Executive dashboards.
- Approver group is configurable by the Super Admin (Founder, Executive Director, optional acting approver with start/end dates for when the Founder is away). Approval uses re-authentication (password + 2FA). Every approval, rejection and override is immutably audit-logged. Notify requesters by email without sensitive details.

4. MONTHLY PERFORMANCE TARGETS
- Build an Indicator framework from the approved annual strategic plan: categories evangelism, discipleship, youth fellowships, membership, partnerships, missions, finance, development, media, prayer. Each indicator: name, unit, owner department, annual target, monthly targets (auto-split but editable), branch scope (ministry-wide or per branch), financial year.
- Add an admin screen to enter/import the strategic plan targets (CSV import with validation) and let authorized leadership adjust them; keep a change history (who, old and new value, reason).
- Departments enter monthly actuals in their dashboards; show target vs actual, percent achieved, trend and red/amber/green status. The Executive Overview shows all categories at once, with overdue reporting flagged. Seed clearly fake sample targets for demo only.

5. BRANCH COORDINATOR + DEPARTMENT ACCESS
- Make scope a property of EACH role assignment, not of the user. DepartmentMembership gets a scope: "all branches" (department leaders) or "single branch" (a Branch Coordinator who also serves in a department). A Branch Coordinator in a department sees only that branch's records inside that department, and nothing from other branches or other departments. Department leaders see their department across all branches.
- Enforce in querysets, views, exports, reports, search and dashboard aggregates (KPI cards and charts must respect scope too). Test combinations: coordinator-only, coordinator + department, leader, multi-department user, and attempts to guess IDs from another branch.

6. DEVELOPMENT <-> FINANCE INTEGRATION
- Link Development projects to Finance directly: each project has a budget (a Finance budget line/cost centre) and project costs are the Finance ledger entries tagged with that project. NO duplicate transactions: the project page reads from the ledger, and recording a project expense happens by creating a ledger entry (with project and budget-line references) that follows rule 3 approvals.
- Project dashboard: budget, committed, spent, remaining, variance, milestone progress vs money spent, and alerts for overspend and unbudgeted costs. Finance sees the same entries in the ledger; Development sees only its projects' cost summaries and entries it is permitted to view. Same pattern for Logistics purchase orders and Missions budgets: one ledger, referenced everywhere.

7. PRINTABLE REPORTS (browser print, no server PDF for now)
- Create print stylesheets and "Print / Save as PDF" buttons for all reports (membership, finance, procurement, missions, discipleship, media, development, executive, indicator reports, member/volunteer lists).
- Every printable report must include: ministry logo and name, report title, department, branch (or "All branches"), reporting period and financial year, generated date and time, generated by, page numbers, a footer with confidentiality notice for sensitive reports, and an APPROVAL SECTION (Prepared by / Reviewed by / Approved by with name, signature and date lines). Use brand colours with good print contrast, A4 layout, no cut-off tables, and a clean black-and-white fallback. Hide navigation and buttons when printing. Printing sensitive reports is permission-gated and audit-logged.
- Structure the report templates so that server-side PDF generation can be added later without rewriting them (keep print views as standalone templates).

8. APPLICATION RETENTION
- Applications (membership, discipleship, partnership, finance-volunteer) have statuses: pending, approved (successful), unsuccessful. Successful applications are converted into the proper ministry records (member register, discipleship cohort, partner pipeline, vetted finance-volunteer list) and the application keeps only a reference.
- Unsuccessful applications are retained for 365 days from the decision date, then automatically anonymized or deleted by a scheduled Celery job: delete personal data, encrypted essays and contact details, keeping only non-identifying statistics (type, branch, month, outcome) for reporting. Make the retention period a setting, log each purge run in the audit log, and give Super Admin a dry-run preview. Support early deletion on a person's valid request and a legal-hold flag that pauses deletion. Show the retention deadline in the application screen and send the department head a monthly report of applications nearing purge. Tell applicants about the retention period on the form and in the privacy policy, and update the privacy policy accordingly. Apply the same rules to any minors' data (stricter visibility, never kept longer than needed).

## D-026: Branch scope per role assignment (ministry decision 5)
(2026-11-20) `DepartmentMembership.branch`: empty = all branches, a branch = single-branch assignment. The
Super Admin sets it per department on the roles screen. `Access.branch_scope(department)` drives every
queryset (`Resource.get_queryset`), dropdown, export, file download, search, dashboard figure, chart, monthly
report and "Our budget". Choices made:
* A single-branch assignment sees only records **of that branch**: records with no branch (ministry-wide) or of
  other branches are hidden, and screens whose records have no branch at all (e.g. the media content calendar,
  donors, suppliers) show nothing. Safe default; open a question if a department needs ministry-wide records.
* The coordinator-only role (Branch Coordinator without a department) keeps branch-level read access to
  Membership, Missions and Discipleship for `user.branch`.
* Requests shared with requesting departments (purchases, design requests): an all-branches assignment sees its
  department's requests; a single-branch assignment sees only the requests it filed itself.
* Migration: existing department assignments of Branch Coordinators became single-branch for their branch, so
  nobody gained access. Finance budget lines and ledger entries gained an optional branch (empty =
  ministry-wide) so finance can be scoped and reported by branch.

## D-027: Financial year (ministry decision 2)
(2026-11-20) `finance.FinancialYear` (one row per calendar year, created on demand; the current year is the
default). Budget lines and ledger entries are linked to their year; monthly reports carry their year.
Dashboards and the Executive Overview filter by **financial year** and **whole year / quarter / month** (a free
date range still works through links). Choices made:
* A closed year accepts **no** new, changed, deleted or posted ledger entries and no budget changes, enforced in
  the model (`ClosedYearError`), the forms and the approval service. Corrections to a closed year go into the
  open year (reversals are dated today).
* A year can only be closed when every entry in it is posted (no drafts, rejected or waiting entries), so nothing
  is left stranded.
* Closing: Finance head or Super Admin. Reopening: Super Admin only, after password + 2FA re-authentication, with
  a written reason. Both are in the audit log (`year_closed`, `year_reopened`).
* The re-authentication page is now available to every signed-in staff member (approvers need it); it only
  confirms identity and grants nothing.

## D-028: Executive approval of every expenditure and commitment (ministry decision 3)
(2026-11-20) `finance/approvals.py` holds the single approval path; `/portal/approvals/` is the inbox.
* **What needs approval:** expenditure ledger entries (any payment: project payments, reimbursements,
  purchase-order payments, reversals of expenditure), purchase requests (after Finance has checked the budget),
  outreach campaign and mission-trip budgets, event (logistics plan) budgets, and budget lines themselves. The
  Logistics head no longer approves purchases and Finance no longer approves expenditure; the approval
  threshold was removed. Income is still approved inside Finance by someone other than the recorder.
* **Approvers:** `finance.Approver` rows (Founder, Executive Director, acting approver with start and end dates),
  managed only by the Super Admin with re-authentication. Until the first row exists, active Super Admins
  approve; once any row exists, only current rows count.
* **Segregation:** the recorder, requester, budget submitter, or the Finance person who checked a purchase's
  budget can never decide that item, even when they are an approver.
* **UNBUDGETED** = no budget line, a line not yet approved, more than the line's remaining balance (budget +
  adjustments − posted spending − open approved commitments), or a payment larger than what is left of the
  approved commitment it belongs to. Approving it needs a written justification; when Finance settings switch on
  "requires adjustment", also a reallocation from another approved line with enough balance or a supplementary
  budget covering the shortfall (`BudgetAdjustment`, permanent). Shown first in the inbox and on the Finance
  dashboard and Executive Overview.
* **Records:** every decision is written to the append-only `ApprovalDecision` table (approved / not approved,
  unbudgeted, override, justification, approver and role) and the audit log; the requester gets an email with the
  item type and number only.
* Campaigns with a budget cannot be marked approved/in progress/completed until the budget is approved; approval
  moves a planned campaign to approved. Existing budget lines were migrated as approved; new ones start as drafts.

## D-029: One ledger for projects, purchase orders and campaigns (ministry decision 6)
(2026-11-20)
* `Project.budget_line` (one-to-one) is the project's cost centre; the project budget is that line's approved
  amount plus approved adjustments. The free-typed `Project.budget` and the separate `ProjectExpense` table were
  removed.
* A project cost IS a Finance `LedgerEntry` tagged with `project`. Development records it under "Project costs"
  (a draft expenditure charged to the project's line), submits it, and it follows executive approval (D-028).
  Finance sees the same entry in the ledger; there is no copy. Development sees only project-tagged entries:
  number, date, description, amount, status. Never receipts, payees or other departments' entries.
* Project screen and dashboard: budget, committed (submitted costs + approved commitments on the line),
  spent (posted), remaining, money spent % against milestones done %, alerts for overspent, UNBUDGETED costs,
  money ahead of progress (spent % more than 20 points above milestones %), and projects without a line.
* Same pattern: ledger entries can reference a purchase order, campaign or event plan; the purchase order and
  campaign screens show what has been paid from the ledger, and approved commitments reduce the line's remaining
  balance until paid.
* **Migration of existing data:** each project budget became a DRAFT Development budget line (needs approval);
  each old project expense became a DRAFT expenditure entry tagged with the project, with its old voucher number
  in `reference`. Finance checks these against the books and submits or deletes them; nothing was posted
  automatically, so nothing is counted twice.

## D-030: Executive Finance page (ministry decision 1)
(2026-11-20) `/portal/executive/finance/` (`finance/executive.py`), for Executive Leadership, the Founder /
Super Admin and Finance staff. Every figure is an aggregate: income, expenditure and net for the chosen period;
cash position (all posted income less all posted expenditure up to the period end: the ledger has no opening
balances, so this is the ledger-derived position); outstanding pledges (total and count, no donors); approved
budget for the financial year (approved lines + approved adjustments; drafts excluded); budget vs actual by
department and by branch (lines and spending without a branch shown as "Ministry-wide"); monthly income and
expenditure for the year; income by source; items waiting for executive approval and UNBUDGETED spending.
Filters: financial year, quarter or month, branch. Drill-down: a department's category totals, never entries.
No query on this page returns a ledger line, donor, voucher, receipt, payee or description; ledger, donors,
pledges, donations and exports remain Finance + Founder only (tested). Each view is audit-logged.

## D-031: Monthly performance targets (ministry decision 4)
(2026-11-20) `portal/indicators.py`, screens under `/portal/targets/`.
* `Indicator` now has a category (Evangelism, Discipleship, Youth fellowships, Membership, Partnerships,
  Missions, Finance, Development, Media, Prayer), owner department, unit, financial year, branch (empty = all
  branches), annual target and twelve editable `MonthlyTarget` rows. The split is even for numbers and money
  (rounding goes to December) and the same level every month for percentages.
* Who: the Founder / Super Admin and Executive Leadership create, adjust and import targets ("leadership").
  Department heads no longer define targets. Department members (within their branch scope) record monthly
  actuals; actuals cannot be entered for months that have not started.
* Every change (annual or monthly, by screen or import) writes an append-only `TargetChange` (who, old, new,
  reason); a reason is mandatory. Changing monthly targets of a count/money indicator moves the annual target to
  their sum, also recorded.
* CSV import: fixed columns (template download), every row validated first, nothing imported if any row is
  wrong, preview, then confirm; updates of existing targets recorded as changes. 512 KB / 1,000 rows cap.
* Status: year-to-date target vs actual (sum for counts/money; latest month for percentages), percent, monthly
  trend, RAG = Green at 90%+ of target, Amber 70-89%, Red below 70% (inverted for lower-is-better). A month's
  actual is overdue when still missing on the 10th of the following month (months before the target existed
  are not chased). These thresholds are constants in `portal/indicators.py` (defaults, see final report).
* Executive Overview shows every category (green/amber/red/overdue counts) and the overdue list.
* Existing indicators were migrated: per-period target -> annual target (x12 monthly, x4 quarterly; percentages
  unchanged), year = year created, category from the department (Logistics -> Development).
* `seed_indicators` is demo-only: nothing without `--demo`; samples are named "[DEMO] ...", flagged `is_demo`,
  badged "Demo", and removed with `--remove`.

## D-032: Application retention (ministry decision 8)
(2026-11-20) `core/retention.py`; Super Admin screen `/portal/retention/`.
* The four application types and their records: membership (`membership.Member`), discipleship
  (`discipleship.Registration`), partnership (`giving.PartnershipEnquiry`) and finance volunteer
  (`finance.FinanceVolunteer`). Each has `outcome` (pending / successful / unsuccessful), `outcome_at` (the
  decision date that starts the retention clock), `legal_hold` + reason and `record_reference`. The outcome
  follows the status automatically; partnership registrations get it from two Finance-head actions
  ("Taken forward: partner pipeline" / "Not taken forward").
* **Conversion (default chosen):** a successful membership application IS the member-register entry and a
  successful finance-volunteer application IS the vetted-list entry: the same row moves on, so no second copy of
  anyone's data exists and the reference is "Member register" / "Vetted finance-volunteer list". A discipleship
  registration becomes a Disciple (+ cohort enrolment) and a partnership registration a partner-pipeline record;
  their application rows are then emptied of personal data and keep only "Disciple #n" / "Partner #n".
* **Unsuccessful:** deleted `SiteSettings.retention_unsuccessful_days` (365) after the decision; applicants under
  18: `retention_unsuccessful_minor_days` (90, never longer than the adult period; 0 for adults switches deletion
  off for everyone). The row, everything that cascades from it and their stored files are deleted; for a
  partnership registration the prospect created from it goes too (unless it already has pledges, then it is only
  unlinked). Only `ApplicationStat` (type, branch, month received, outcome, count) remains.
* Jobs: `core.tasks.purge_unsuccessful_applications` nightly 02:30 (every run audit-logged, also when nothing was
  due); `core.tasks.report_applications_nearing_purge` on the 1st of each month to the heads of the owning
  departments (Membership; Discipleship; Finance for partnership and finance volunteers): counts only, deadlines
  within `retention_notice_days` (30) and legal holds. `manage.py purge_applications --dry-run` and the Super
  Admin screen show what would be deleted without deleting.
* Legal hold (Super Admin, reason required) pauses deletion. Early deletion on a person's valid request (Super
  Admin, re-authentication, a note of how the request was verified; refused while on hold; a live member or
  volunteer record goes through the existing data-subject erase instead). Both audit-logged.
* Minors: pending/unsuccessful membership applications of under-18s are visible to the Membership head only
  (discipleship already hid minors from non-heads), and they are deleted sooner.
* The retention deadline is shown on each application screen. Applicants are told on all four forms (from the
  live settings), and the privacy policy gained an "Applications" section plus the live periods in its facts list.
  Existing applications were back-filled from their status (clock from `decided_at`, else last change).

## D-033: Printable reports (ministry decision 7)
(2026-11-20) `portal/printing.py`, `portal/print_views.py`, templates in `templates/print/`.
* Every report prints from a **standalone** template extending `print/base.html` (no portal chrome, laid out by
  CSS only), so the same templates can feed a server-side PDF renderer later without changes. Reports:
  department dashboards (all seven, incl. procurement), Executive overview, Executive finance, performance
  targets, monthly department reports, and every resource list (member register, finance volunteers, purchase
  orders, ...). Each shows logo and ministry name, title, department, branch or "All branches", period and
  financial year, generated date/time and by whom, page numbers, a CONFIDENTIAL footer for sensitive reports
  (finance, membership, discipleship dashboards and reports; every resource marked sensitive; Executive
  finance) and an approval section (Prepared / Reviewed / Approved by with name, signature and date lines;
  "Prepared by" is pre-filled on monthly reports).
* Print CSS: A4 portrait, 15/12/20 mm margins, "Page n of m" via `@page` margin boxes, repeating table headers,
  rows never split, long values wrap instead of being cut off, toolbar/navigation/buttons hidden, brand colours
  kept with `print-color-adjust` while all text is black and every status is written as a word (black-and-white
  printers lose nothing).
* Permissions: a list prints only for users who may export it; personal/financial dashboards print only for the
  department head or Founder; other dashboards for anyone who can open them. Every print is audit-logged
  (`AuditLog.Action.PRINT`) with title, filters and row counts, never record contents. Lists print up to 2,000
  rows (the page says when it is cut).
* The old `<dept>/export/print/` URL was replaced by `<dept>/print/`; CSV export is unchanged.

## Website requirements update (Nov 2026)

Received 2026-11-21 in five parts: (1) Activities replace the five programmes; (2) the official Vision and
Mission, verbatim, with an approval flow; (3) hero background options; (4) a Technical Team role with separation
of duties and protected bank details; (5) strict validation of every upload. How each was implemented, and the
defaults chosen where the requirements left something open, are in D-034 to D-038. Items the ministry must
confirm are marked **Confirm**.

## D-034: Technical Team (Website Administration) and separation of duties (Part 4)
(2026-11-21)
* **Role:** Django group "Technical Team" (`accounts.roles.TECHNICAL`), assigned only by the Super Admin on the
  roles screen (re-authentication, like every role). It is not a department: it has no portal records, lands on
  `/portal/website/` (dashboard: drafts awaiting publish, pages needing updates, recent changes, broken links and
  missing images, site health with uptime and last backup, upload storage use) and edits content in the Django
  admin. Its permission set is in the role matrix; `TECHNICAL_FORBIDDEN_APPS/MODELS` lists what it may never
  hold (finance, giving, donors, members, prayer, discipleship, registrations, contact, accounts, audit, portal,
  system settings, upload limits), and a test fails if the matrix ever grants one.
* **Settings split into three models so access is structural:** `core.SiteContent` (what visitors see: name,
  logos, favicon, Vision/Mission, about text, public email/phone/WhatsApp/address, footer: Technical Team +
  Super Admin), `core.SiteSettings` (system: notification inbox, analytics, retention periods, approval rule:
  Super Admin only) and `giving.GivingSettings` (Finance only). The data moved with a migration; nothing was lost.
  Branch addresses and phones stay on each branch (Technical Team may edit branches).
* **Media & Communications keeps** its existing website rights (news, gallery, resources, slides, page text);
  both teams' edits are versioned. **Missions** now has view-only access to activities (they are website content).
* **Versioning:** every add/change/delete of a Technical Team model (admin or portal) stores an append-only
  `ContentVersion` snapshot plus an audit-log entry; "Changes and rollback" restores any version in one click
  (deleted items too) and records the rollback as a new version. Vision/Mission have their own history
  (D-036); bank details are never versioned there (they have their own, below).
* **Bank and payment details (fraud prevention):** bank transfer and mobile-money fields can only change through
  `giving.BankDetailChange`: the Finance & Resource Mobilization head (or Super Admin) proposes after password +
  2FA; it is saved as pending (one at a time); an email alert goes to the Finance heads and the Super Admins with
  the last four digits only; a second person - Founder or Executive Director (Super Admin or `finance.Approver`
  row), never the proposer - confirms after password + 2FA; only then the details go live and "Last verified"
  (shown on the Give page) is set. Rejections and cancellations are kept; rows cannot be deleted; the replaced
  details are stored encrypted on the change. `GivingSettings.save()` refuses any other change, and the Django
  admin no longer shows these fields. Only the Finance head, the Founder/Executive Director and the Super Admin
  can open the screens; ordinary Finance members cannot (default chosen: **Confirm**).
* **Finance enquiries go only to Finance:** the contact form has a "Subject: General / Giving and finance /
  Partnership" selector. Giving and partnership messages appear only in Finance > "Giving and partnership
  enquiries" (portal) and are hidden from the general contact list in the admin (Membership); their alerts, and
  alerts for partnership registrations, pledges and finance-volunteer applications, go to the Finance heads
  instead of the general notification inbox.
* **Backups:** `docker/backup/backup.sh` writes ok/failed (no names or sizes) to `core.BackupRun` for the
  dashboard; more than 36 hours since the last success shows a warning.

## D-035: Activities replace the five programmes (Part 1)
(2026-11-21) `programs.ActivityCategory` and `programs.Activity` (title, slug, summary, body, image, icon,
schedule/frequency, branches (empty = all), department, "Get involved" button, order, published, featured, SEO).
Seeded with exactly the four categories and thirteen activities given; summaries are short neutral placeholders
for the Technical Team to replace. Pages: `/activities/` (grouped by category), `/activities/category/<slug>/`,
`/activities/<slug>/` (related upcoming events, "Get involved" and "Support this activity"); the home page shows
each category as a card carousel; About lists the categories. Old `/programs/...` URLs redirect permanently.
* **Department routing (defaults, Super Admin changes them; ministry must confirm):** Charitable and
  Humanitarian Services -> Development & Infrastructure; Evangelism and Missions -> Missions & Outreach;
  Discipleship -> Discipleship; Revival Programme -> Missions & Outreach. **Confirm.** Each department dashboard
  shows "Our activities" (upcoming events, open campaigns / classes, targets this year; branch-scoped).
  `Activity.department` is read-only in the admin for everyone but the Super Admin; a category's department is
  the default for new activities in it.
* **Links:** events, outreach campaigns, discipleship classes and indicators (targets) can reference an activity;
  the event admin filters by activity and category; the finance budget category "Programmes & events" is now
  labelled "Activities & events" (same code, no data change).
* **Old programme data:** programme text, image and SEO that staff had written were copied to the activity that
  replaced the programme (Youth Revival Conferences -> Annual Youth Revival Conference, Prayer & Intercession ->
  Prayer and Intercession, Discipleship -> Mentorship Programme, Youth & Leadership Development -> Leadership and
  Ministerial Trainings; Evangelism & Missions text went to its category, as it covers three activities). Events
  were relinked the same way; events of "Evangelism & Missions" are left unlinked for staff to assign. Any
  programme the ministry had added itself became an unpublished activity under Revival Programme for review.
  The programme table was then removed.

## D-036: Vision and Mission, verbatim, with approval (Part 2)
(2026-11-21) Seeded by migration `core 0015` exactly as received; `tests/test_vision_mission.py` asserts both
strings character for character and that no template or code carries a second copy. They are printed only from
`SiteContent` (home and About through `includes/vision_mission.html`, the footer, and the default meta
description = the Mission cut at 160 characters).
* The fields are not editable in any form. Changes go draft -> preview (real layout, side by side with the
  published text) -> submit -> approval by the Super Admin or the Executive Director (`finance.Approver` row with
  role Founder/Executive Director), never the author, after password + 2FA -> publish (by the author or an
  approver). A rejection needs a reason. Other open changes to the same field are marked "superseded" when one
  is published. Every step is audit-logged.
* "Approval required" is `SiteSettings.vision_mission_approval_required` (default ON, Super Admin only). When
  off, the Technical Team publishes after preview; history still records it.
* Version history = the published changes; "Restore this version" proposes the earlier text again: one click
  (with re-authentication) for an approver, otherwise it waits for approval.

## D-037: Hero background options (Part 3)
(2026-11-21) `core.HeroContent` (shared by the home hero `HeroSettings` and each `HeroSlide`): headline,
sub-headline, up to two buttons (labels + links validated as site paths or https, re-checked when shown), text
alignment (left / centre), text colour (light / dark preset), show scripture, and background "Theme colour"
(default), "Photo" or "Video".
* **Fallback:** a photo without a file, or a video without its file or poster, is shown as the theme colour.
  Without JavaScript, or when the video may not play, the poster shows.
* **Photo:** hero-photo upload policy (JPEG/PNG/WebP, 5 MB, at least 1600 px wide), WebP srcset 480/960/1600,
  focal point (0-100 % across and down, used as `object-position`), dark overlay 0-80 % (default 45 %).
* **Video:** hero-video policy (MP4 H.264 or WebM, 15 MB, 15 s, no audio track - the file must be silent, a
  default chosen so no sound can ever play; **Confirm**), required poster. Rendered `muted loop playsinline
  preload="none"` without a `src`; `static/js/hero-video.js` adds the source only after the load event and idle
  time, and only when reduced motion is not requested, Save-Data is off, the connection is not 2G/3G or under
  1.5 Mbit/s, and on phones only on a 4G-class connection. A visible button pauses it; off-screen videos pause.
  CSP gained `media-src 'self'`; videos come from our own storage only. The admin shows the recommendation
  (<= 10 s loop, 1080p, under 10 MB).
* **Readability:** on upload, the brightest 10 % of the photo/poster is measured; with the overlay blended in, the
  contrast against the text colour is computed (WCAG formula). Below 4.5:1 the portal, the admin and the dashboard
  warn (not blocked). The portal editor shows the same check live while editing.
* **Draft, preview, publish, revert:** the home hero has a draft and a live row; the portal editor
  (`/portal/website/hero/`) edits the draft with a live preview, "Preview the draft full size" shows it on the real
  layout (not indexed), "Publish draft" copies it to live (versioned) and "Revert to previous" restores the previous
  live hero. Slides: save switched off, preview (works while off), switch on; any earlier version can be restored.
  The old "home_hero" page text was folded into the hero settings and removed.

## D-038: One upload policy for every file field (Part 5)
(2026-11-21) `core/upload_policy.py` holds the policy table; `SafeImageField`, `SafeFileField` and
`PrivateFileField` require `policy=` and validate in every ModelForm and again before storing. Policies as given;
**defaults chosen for fields the table did not name (Confirm):** partner logos, branch, event and testimony
images use "content image" (3 MB); album covers "gallery photo"; member documents, meeting minutes and
correspondence "private record" (PDF/JPEG/PNG, 10 MB); the media design-request artwork "design file"
(PDF/JPEG/PNG/WebP, 20 MB); discipleship curriculum files "study material" (PDF, 10 MB, private); quotations and
property title documents "office document"; delivery notes "receipts and vouchers"; field photos (Missions)
"site photo". The new favicon field is PNG only, 2 MB.
* Super Admin adjusts size, minimum width and video length per policy in Admin > Upload limits (never above the
  60 MB request cap or 30 s); formats are fixed in code.
* Video is parsed in-house (MP4 boxes, WebM/EBML): no ffmpeg or new package. PDFs are scanned (including inflated
  streams, name obfuscation `#xx`) for JavaScript, launch/submit actions, embedded files, rich media, XFA and
  encryption; DOCX/XLSX are opened as zip and refused with macros, ActiveX, embedded objects, encryption, path
  tricks, more than 2,000 parts, 200 MB uncompressed or a 100:1 ratio on a large part.
* ClamAV is optional (`CLAMAV_ENABLED`, `docker compose --profile clamav`), on the private network plus an
  egress-only network for signature updates; when enabled and unreachable, uploads are refused (fail closed).
  **Confirm** whether to run it (about 1.5 GB RAM).
* Request bodies: Caddy 60 MB; Django middleware 1 MB on public pages (they take no files) and 60 MB for the admin
  and portal; `DATA_UPLOAD_MAX_MEMORY_SIZE` and `FILE_UPLOAD_MAX_MEMORY_SIZE` 2 MB (larger files are streamed to a
  temporary file). CSV import uses the "CSV import" policy (2 MB, UTF-8) plus the existing row validation; CSV
  exports neutralise formula cells, now also after leading spaces.
