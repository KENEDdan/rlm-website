# Threat model: staff portal, departments and accounts

**Updated:** 2026-11-19 · Complements `SECURITY_AUDIT.md` (re-run 2) and `INCIDENT_RESPONSE.md`.

## 1. What we protect (assets)

| Asset | Where | Why it matters |
|---|---|---|
| Faith and pastoral data: testimonies, born-again/baptism answers, **pastoral notes**, check-ins, welfare cases | membership, discipleship, missions (encrypted fields) | Deeply personal; in some places exposure can endanger people |
| Children's records (under 18) | members, registrations, converts | Legal and safeguarding duty |
| Contact details of members, converts, partners, donors, community contacts | encrypted fields + blind-index hashes | Spam, scams, targeting |
| Financial records: ledger, receipts and vouchers, budget, donors, pledges | finance (posted entries immutable) + private files | Fraud, donor trust, accountability to partners |
| Bank and mobile-money details | `GivingSettings` (encrypted) | Redirection of gifts |
| Legal documents: title deeds, permits, contracts | development private files | Property disputes |
| **Accounts and roles** | `accounts`, `portal.DepartmentMembership`, groups | Whoever controls these controls everything above |
| Audit log | `audit` (append-only, DB trigger) | Evidence after an incident |

## 2. Who might attack (actors)

1. **Outsider on the internet:** bots on public forms, credential stuffing, phishing staff.
2. **Curious or careless insider:** a staff member looking at records outside their work (another
   department, another branch, children's or pastoral records), or exporting too much.
3. **Malicious insider:** a department head trying to give themselves or a friend more access, a recorder
   trying to approve their own payment, a requester approving their own purchase.
4. **Compromised staff account:** stolen password plus SIM/phone theft, an unlocked laptop.
5. **Server-level attacker:** shell or database access (stolen backup, compromised host).

## 3. Trust boundaries
Internet → Caddy (TLS, headers, never serves `/uploads/private/*` and never mounts the private volume) →
Django (public pages, public forms) | staff sign-in (password → TOTP) → **portal** (department scoping) and
**admin** (website content; account screens read-only) → PostgreSQL / Redis on the internal network only.

## 4. Threats and mitigations

| # | Threat (STRIDE) | Mitigation | Evidence |
|---|---|---|---|
| T1 | Self-registration or account creation by an outsider (Elevation) | No signup, social login or API; public forms create records only | `test_no_unauthenticated_url_can_create_a_user`, `test_there_is_no_api` |
| T2 | Head grants themselves or others a role (Elevation) | Only `accounts.services` change accounts/roles; every function re-checks "active Super Admin"; no self-edit; admin user screens read-only; Founder group has no account permissions | `test_other_roles_cannot_manage_accounts[*]`, `test_services_refuse_non_super_admins_even_if_a_view_forgot[*]`, `test_department_head_cannot_grant_roles` |
| T3 | Stolen Super Admin session performs account changes (Spoofing) | Re-authentication (password + fresh TOTP, 5 minutes) for every account change; session timeout 2 h | `test_reauth_is_required`, `test_reauth_expires` |
| T4 | Super Admin lock-out or takeover by adding more Super Admins | Max 2 active; last one cannot be demoted, deactivated or deleted; Super Admins never auto-disabled | `test_only_super_admin_creates_super_admin_and_limit_applies`, `test_last_super_admin_cannot_be_demoted_deactivated_or_deleted` |
| T5 | Intercepted or guessed invitation (Spoofing) | 256-bit single-use token, only SHA-256 stored, 48 h expiry, revocable, older links revoked on resend, rate-limited, identical response for every invalid link, no password ever emailed; TOTP enrolment forced before any page | `test_invite_flow_single_use_and_2fa_forced`, `test_invite_expiry_and_revocation` |
| T6 | Account/role changed in a shell or with SQL (Tampering, Repudiation) | Model guard audits every change with old/new values and alerts Super Admins when not sanctioned; 15-minute HMAC fingerprint catches raw SQL | `test_out_of_band_change_is_detected_and_alerts`, `test_integrity_check_catches_raw_sql` |
| T7 | Leaver keeps access (Elevation) | Deactivation kills all sessions immediately; dormant accounts flagged at 60 and disabled at 90 days; quarterly access review | `test_deactivation_kills_sessions_and_is_audited`, `test_dormant_accounts_flagged_then_disabled` |
| T8 | Staff of one department read another's records (Information disclosure) | One scoping path for every screen, export and file; out-of-scope objects are 404; dropdowns limited; post-save scope check | `test_department_dashboards_are_isolated[*]`, `test_every_registered_resource_denies_outsiders`, per-department tests |
| T9 | Branch Coordinator reads another branch (Information disclosure) | Branch filter on every branch-bound record; filter cannot be widened; no branch = nothing | `test_branch_coordinator_scoped_in_missions`, `test_branch_coordinator_sees_only_own_branch_and_cannot_decide` |
| T10 | Children's data exposed or published | Minors visible to the head and Founder only; guardian consent required; never on mailing lists; testimonies need "18 or over" | `test_minors_visible_only_to_head_and_need_guardian_consent`, `test_testimony_approval_requires_consent_and_adult` |
| T11 | Pastoral notes read by other staff (Information disclosure) | Assigned mentor, Discipleship head and Founder only; never exported; every view audited | `test_pastoral_notes_only_for_mentor_head_and_founder` |
| T12 | Recorder approves their own payment, or a posted entry is altered (Tampering) | Segregation of duties, executive approval (with re-authentication) of every expenditure and commitment, immutability at model/queryset/view level, corrections by audited reversal | `test_recorder_cannot_approve_own_entry`, `test_posted_entries_are_immutable`, `test_reversal_flow` |
| T13 | Requester approves their own purchase or skips quotations (Tampering) | Min. 3 quotations, reason when not the cheapest, Finance budget confirmation, approver ≠ requester | `test_full_procurement_chain`, `test_requester_cannot_approve_own_request_even_as_head` |
| T14 | Malicious upload / direct file access (Tampering, Disclosure) | ONE upload policy per field (core/upload_policy.py): name, extension, magic bytes matching the extension, size, pixels, video container/codec/length, PDF actions, Office macros and zip bombs, no SVG/HTML/executables; optional ClamAV; images re-encoded; random names; private volume; permission-checked audited download | `tests/test_upload_policies.py` (malicious samples, every field has a policy) |
| T15 | Bulk data theft through exports (Disclosure) | Exports head-only, audit-logged, CSV-injection safe; pastoral notes never exportable | `test_dashboard_export_is_head_only_and_audited`, export cases in every department test |
| T16 | Form spam / abuse (Denial of service) | CSRF, honeypot, Turnstile, per-IP rate limits | `test_honeypot_blocks_all_four`, existing form tests |
| T17 | XSS through data shown in charts and lists (Tampering) | Auto-escaped templates only (no `|safe`), SVG geometry computed in Python, nonce CSP without inline scripts | grep in SECURITY_AUDIT re-run 2 |

| T18 | Payment-detail fraud: someone swaps the bank account donors pay into (Tampering) | Two-person rule: Finance head proposes with re-authentication, Founder/Executive Director confirms with re-authentication; masked email alerts; history; model refuses any other change; "Last verified" on the Give page | `tests/test_technical_team.py` bank tests |
| T19 | Website defacement or wrong Vision/Mission by a content editor (Tampering) | Technical Team limited to website content; Vision/Mission need approval; every change versioned with one-click rollback and audit log | `tests/test_technical_team.py`, `tests/test_vision_mission.py` |

## 5. Residual risks
See `SECURITY_AUDIT.md` R2.4: shell/database access is detected rather than prevented; invitation tokens may
appear in proxy logs; Executive Leadership sees ministry-wide totals; ages are self-declared.
