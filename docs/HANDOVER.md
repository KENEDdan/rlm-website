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

1. On the server: `docker compose -f docker-compose.prod.yml exec web python manage.py create_founder --email <founder email> --name "<full name>"`
   The Founder types the password themselves (12+ characters, a passphrase they use nowhere else).
2. The Founder **immediately** opens `https://<domain>/<DJANGO_ADMIN_URL>account/login/`, signs in, scans the
   QR code with an authenticator app on their own phone, and enters the code.
3. The Founder writes the **10 backup codes** on paper (kept in a safe) and stores them in the password
   manager.
4. Repeat for the deputy (second Founder) so the ministry is never locked out.
5. The Founder creates the other staff accounts (ADMIN_GUIDE §3.1): one person, one account, the
   **smallest role** that lets them do their work.
6. Remove any developer accounts in the admin that are no longer needed (Users > untick Active).

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

### Every form tested on the live site (Secretary)
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
| Secretary | Handling submissions, form options, exports and why to avoid them | ADMIN_GUIDE §2 |
| Founder + deputy | Users and roles, Site settings, pages, audit log, data requests | ADMIN_GUIDE §3 |
| Programs & Events | Events, capacity, registrations | ADMIN_GUIDE §4 |
| Media & Communications | Page text, news, albums, videos, resources, consent for photos | ADMIN_GUIDE §5 |
| Finance | Giving settings, confirming gifts, receipts | ADMIN_GUIDE §6 |
| Branch Coordinators / Department heads | Their own branch or department only | ADMIN_GUIDE §7–8 |

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
