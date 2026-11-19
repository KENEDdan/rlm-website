# Handover to the ministry

This is the checklist for handing the website to Rebuilding Lives Ministry so that **the ministry owns and
controls everything**, and no single developer or volunteer can lock it out. Tick each box and keep a copy
of this page with the date and the name of who did it.

Related: `docs/DEPLOYMENT.md` (server), `docs/ADMIN_GUIDE.md` (daily use),
`docs/STAFF_SECURITY_SHEET.html` (print one per staff member), `docs/INCIDENT_RESPONSE.md`.

---

## 1. Ownership transfer

Every account below must be **registered to a ministry email address** (e.g. `admin@<domain>`, not a
personal Gmail), with **two owners** (the Founder and one trusted deputy), **two-factor sign-in on**, and the
recovery codes stored in the ministry password manager.

| ✓ | Account | Owner checks |
|---|---|---|
| ☐ | **Password manager** (e.g. Bitwarden Organisation, 1Password Teams) | Founder + deputy; this is where every login, the encryption keys and the backup key live |
| ☐ | **Domain registrar** | Registered to the ministry (legal name), ministry contact email, auto-renew on, registrar lock on, 2FA on |
| ☐ | **Cloudflare** | Ministry owns the account; developer invited as a member with limited role; DNS records match `docs/DEPLOYMENT.md` §1 |
| ☐ | **VPS / hosting** | Billing in the ministry's name; developer has a separate user; root/console password in the password manager |
| ☐ | **Server SSH** | Ministry holds its own key; developer keys listed by name in `/home/rlm/.ssh/authorized_keys` and removable |
| ☐ | **GitHub organisation** | Ministry organisation owns the repository; Founder + deputy are owners; developers are members, not owners; 2FA required for the organisation |
| ☐ | **Transactional email provider** | Ministry account; SPF, DKIM and DMARC records verified |
| ☐ | **Ministry mailbox** for staff alerts (Site settings > Notification email) | A shared ministry inbox, not a personal one |
| ☐ | **Off-site backup storage** | Ministry account; the server's key can write but not delete; lifecycle rule set |
| ☐ | **Uptime monitor / Sentry** | Alerts go to the Founder and the technical lead |
| ☐ | **Social media accounts** linked from the site | Ministry-owned, 2FA on |

### Secrets that must be in the ministry password manager (never in email or chat)

| ✓ | Secret | Why it matters |
|---|---|---|
| ☐ | `FIELD_ENCRYPTION_KEYS` and `BLIND_INDEX_KEY` (from the server `.env`) | Without them, every prayer request, volunteer and donor record is **unreadable forever** |
| ☐ | The **age private key** for backups | Without it, backups cannot be restored |
| ☐ | The whole server `.env` (a copy) | Rebuilding the server after a disaster |
| ☐ | Founder and deputy **backup codes** for the website | Signing in if a phone is lost |
| ☐ | Registrar, Cloudflare, hosting, GitHub, email and storage logins + their recovery codes | Control of the ministry's internet presence |

**Test:** the deputy (not the developer) signs in to each account above once and confirms access. ☐

---

## 2. The Founder's website account

Done once, by the technical lead, **with the Founder present**:

1. On the server: `docker compose -f docker-compose.prod.yml exec web python manage.py create_super_admin`
   It asks for the email and name; the Founder types the password themselves (12+ characters, a passphrase
   they use nowhere else). It refuses to run once a Super Admin exists.
2. The Founder **immediately** opens `https://<domain>/<DJANGO_ADMIN_URL>account/login/`, signs in, scans the
   QR code with an authenticator app on their own phone, and enters the code.
3. The Founder writes the **10 backup codes** on paper (kept in a safe) and stores them in the password
   manager.
4. The Founder invites the deputy as the second Super Admin from the staff portal (ADMIN_GUIDE §21) so the
   ministry is never locked out (at most two Super Admins).
5. The Founder invites the other staff (ADMIN_GUIDE §21): one person, one account, only the departments and
   head roles their work needs. Then run `manage.py seed_indicators` and set real targets with each head (§18).
6. Deactivate any developer accounts that are no longer needed (Accounts & security > the person > Deactivate).

---

## 3. Launch checklist

Run `docker compose -f docker-compose.prod.yml exec web python manage.py launch_check` on the server. It
checks most of the items below automatically and prints exactly where to fix each one. **Launch only when it
shows 0 blockers** (`launch_check --strict` exits with an error otherwise).

### Content (leadership)
- ☐ About text, vision and mission replaced with the official wording from the brief
- ☐ Privacy policy and terms **reviewed by leadership**, "Draft" heading removed, *Last reviewed* set
- ☐ Real logo uploaded (light + dark versions) if different from the built-in one
- ☐ Officers confirmed by leadership; each leader set to *Confirmed* + *Published* (with consent for photos)
- ☐ Branches: contact details, address and meeting times for Juba and Yei
- ☐ Programmes, upcoming events, first news post, first sermons/resources
- ☐ Real photos uploaded (people photographed have agreed; extra care with children)
- ☐ Page headings and form options reviewed (Page text, Form options)
- ☐ Social media links added; WhatsApp number set
- ☐ No demo content (`launch_check` confirms)

### Giving (Finance)
- ☐ Bank details entered by Finance **and confirmed with the bank by phone**
- ☐ Mobile-money instructions entered (if used)
- ☐ Giving categories and current needs reviewed
- ☐ Test pledge made and confirmed in the admin; receipt email received

### Every form tested on the live site (Membership Administration)
- ☐ Volunteer form → appears in admin, staff alert email received (no personal details in it), acknowledgement email received
- ☐ Event registration → confirmation email; second registration with the same email does not duplicate
- ☐ Prayer request (with and without contact details)
- ☐ Contact form
- ☐ Newsletter: subscribe → confirmation email → confirmed; unsubscribe link works
- ☐ Partnership enquiry
- ☐ Test submissions deleted afterwards

### Security and operations (technical lead)
- ☐ `manage.py check --deploy` and `launch_check --strict` pass
- ☐ All staff have finished two-factor setup
- ☐ HTTPS works, `http://` and `www.` redirect to `https://<domain>`
- ☐ Emails pass SPF/DKIM/DMARC (send a test to a Gmail account and check "Show original")
- ☐ Nightly backup ran (`/var/log/rlm-backup.log`) and the off-site copy arrived
- ☐ **Restore tested** from last night's backup into the scratch database (BACKUP_RESTORE §4)
- ☐ Uptime monitor alerting the Founder and technical lead
- ☐ Lighthouse on the live site: Performance, Accessibility, Best practices and SEO all ≥ 90

---

## 4. Training (about 2 hours, with the handover meeting)

| Who | Covers | Material |
|---|---|---|
| All staff | Signing in with 2FA, the security sheet, phishing, what to do if something looks wrong | `STAFF_SECURITY_SHEET.html`, ADMIN_GUIDE §1 |
| All staff | The staff portal: dashboard, filters, records, Our budget, asking other departments | ADMIN_GUIDE §10 |
| Founder + deputy | Inviting staff and roles, access review, account audit trail, Executive overview, reviewing reports, Site settings | ADMIN_GUIDE §3, §20, §21 |
| Each department head + team | Their department's portal section; targets and monthly report | ADMIN_GUIDE §11–17, §18 |
| Membership Administration | Website submissions, form options | ADMIN_GUIDE §2 |
| Missions & Outreach | Events, capacity, registrations | ADMIN_GUIDE §4 |
| Media & Communications | Page text, news, albums, videos, resources, consent for photos and testimonies | ADMIN_GUIDE §5, §14 |
| Finance | Giving settings, confirming gifts, ledger and segregation of duties | ADMIN_GUIDE §6, §12 |
| Branch Coordinators | Their own branch only | ADMIN_GUIDE §7, §19 |

Each person signs in during the session and finishes 2FA setup before leaving.

---

## 5. First 30 days after launch

- Week 1: check the staff-alert inbox daily; answer every submission; fix wording people find confusing.
- Week 2: DMARC from `p=none` to `p=quarantine` if reports show only legitimate mail.
- Week 4: first monthly routine: restore test, audit-log review, update check (`scripts/deploy.sh` after
  Dependabot updates are merged), review who still needs their admin account.
- Only after a few weeks of stable HTTPS: consider submitting the domain to the HSTS preload list.

---

## Sign-off

| Item | Name | Date | Signature |
|---|---|---|---|
| Accounts transferred (§1) | | | |
| Secrets stored in the password manager (§1) | | | |
| Founder and deputy accounts with 2FA (§2) | | | |
| Launch checklist complete (§3) | | | |
| Training delivered (§4) | | | |
