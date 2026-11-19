# Incident response

What to do when something looks wrong. Act calmly and quickly, write down what you see and when, and
**do not delete evidence** (logs, emails, the audit log).

**Incident lead:** the Founder (or a deputy named by the Founder). **Technical lead:** the website
administrator. Keep both people's phone numbers somewhere you can reach without the website.

> The site currently runs on a local PC only. Sections marked **(server)** apply after deployment
> (phase K).

---

## 0. First 15 minutes (any incident)

1. **Tell the incident lead** by phone. Do not discuss details by email if an email account might be
   compromised.
2. **Write a timeline:** what you noticed, when, which account, what you clicked.
3. **Contain** using the matching section below (disable an account, rotate a secret, take the site offline).
4. **Preserve evidence:** export the audit log view (Founder: **Audit log** in the admin, filter by date or person, and **Account audit trail** in the portal) and
   keep server logs. Do not "clean up" first.

---

## 1. A staff account may be compromised

*Signs: an unknown sign-in in the audit log, changes nobody made, a phishing email someone answered, a
password reused elsewhere that leaked, or an email "Security alert: account change outside the staff
portal".*

All steps are in the staff portal under **Accounts & security**, by a **Super Admin** (each asks for your
password and a fresh authenticator code first).

1. **Staff accounts → the person → Deactivate.** New sign-ins are blocked and **every session they have is
   ended at once**.
2. Same page: **Reset two-step sign-in** and **Force password reset** (the old password stops working; they get
   a single-use link later, only when you reactivate them).
3. **Account audit trail** (and the full audit log in the admin, filtered by that person): list what they
   viewed, exported, changed or deleted since the suspected time, and whether any **account or role** was
   changed. Exports of members, prayer requests, volunteers, donors or pastoral notes are a **data breach**
   (section 5).
4. If the trail shows **"changed OUTSIDE the portal"**, someone changed accounts without these screens (for
   example in the database). Treat the server as possibly compromised too (section 3).
5. Undo unauthorised changes: roles given to anyone (Change roles), content (news, pages, hero slides), and
   **check Giving settings** bank/mobile-money details against the bank by phone (section 4).
6. If the attacker may still hold a session elsewhere, the technical lead can sign **everyone** out by
   restarting with a new `DJANGO_SECRET_KEY` (`docs/BACKUP_RESTORE.md` section 3, last paragraph).
7. Reactivate only after you have spoken to the person in person or by phone; they then set a new, unique
   password and re-enrol their authenticator.

**If a Super Admin account is compromised** (or no Super Admin can sign in): another Super Admin follows the
steps above. If there is none, the technical lead runs on the server:
`docker compose -f docker-compose.prod.yml exec web python manage.py emergency_disable --email <address> --reset-2fa`
It can only remove access, ends all that account's sessions, is recorded in the audit log and emails the Super
Admins. If no active Super Admin remains, `manage.py create_super_admin` creates a new first Super Admin (it
refuses while one is active) and the Founder signs in at once to set up the authenticator.

## 2. A phone with the authenticator app is lost or stolen

1. The person can still sign in with one of their **10 backup codes**, then press **New backup codes**.
2. Otherwise a Super Admin, after **confirming it is really them** (phone call or in person; never by email or
   chat alone): **Accounts & security → Staff accounts → the person → Reset two-step sign-in.** Their old
   authenticator and backup codes stop working and they are signed out everywhere.
3. They sign in with their password and scan a new QR code, then keep the new backup codes safe.
4. If they think someone may also know their password: **Force password reset** at the same time.

## 2a. A staff member leaves (or changes role)

* **Last working day:** Super Admin → the person → **Deactivate** (signs them out everywhere). Do this the
  same day, before handing over equipment.
* Make sure their work is reassigned first: open items they own (follow-ups, mentorships, purchase requests,
  design requests, donor relationships, welfare cases) can be filtered by person in each list.
* Shared things they knew: change any shared mailbox or social media passwords they had, and remove them from
  social media page roles and the domain/hosting accounts if they had access.
* After the retention period you choose (or straight away if they ask), **Delete account**. The audit history
  is kept.
* **Changing role:** **Change roles and departments** and remove what they no longer need. Do not leave old
  roles "just in case": the quarterly **Access review** exists to catch these.

## 3. The PC (now) or server (later) may be compromised

*Signs: unknown programs or processes, antivirus alerts, unknown SSH keys, the site showing content nobody
wrote, unexplained traffic or CPU use.*

1. **Isolate:** disconnect the PC from the network (or, on a server, stop the containers:
   `docker compose -f docker-compose.prod.yml down`; take a provider snapshot first for evidence).
2. Assume **every secret in `.env` is known to the attacker**: Django secret key, database password,
   encryption keys, email password, Turnstile and payment webhook secrets.
3. **Rebuild clean, do not repair:** a freshly installed machine/server, code from the Git repository,
   database restored from the **last backup made before** the suspected compromise.
4. **Rotate every secret** (new values in the new `.env`):
   * `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_ADMIN_URL`; <!-- pragma: allowlist secret -->
   * email/SMTP password, Turnstile keys, `PAYMENT_WEBHOOK_SECRET` (in the provider dashboards too);
   * **field encryption keys**: rotate with `rotate_encryption_keys` (BACKUP_RESTORE §3). Rotation protects
     data from now on; data the attacker already copied together with the old key must be treated as
     exposed (§5).
5. Reset every staff member's password and two-factor.
6. **(server)** Review: SSH `authorized_keys`, users, cron jobs, firewall, Cloudflare account members, DNS
   records, domain registrar contacts, hosting account users. Turn on 2FA on all of them.

## 4. Giving / bank details changed, or payment fraud

*Signs: donors report a different account number; a "please update our bank details" email; pledges that
never arrive.*

1. Founder or Finance: open **Giving settings**, untick **Bank transfer enabled** and **Mobile money
   enabled** until verified. The Give page then shows no account details.
2. **Audit log**, filter "giving settings": who changed what, when.
3. Phone the bank (number from a statement or card, **never** from an email) and confirm the real details.
4. If donors may have paid a fraudster: tell the bank and the police, and post an announcement with the
   correct details on the site and social media.
5. Treat it as §1 (an account was misused) as well.

## 5. Personal data may have been exposed (data breach)

Prayer requests, volunteer testimonies, phone numbers and donor details are sensitive; some concern
vulnerable people.

1. Work out **what** (which records, which fields), **whose** (how many people, which countries) and
   **how** (export in the audit log, stolen backup + key, compromised server).
2. If only encrypted data **without** the keys was taken, the content is protected; record this reasoning.
3. Check legal duties for every country the affected people live in (for example donors in the EU/UK
   under GDPR must normally be reported to the regulator within 72 hours). Get advice if unsure.
4. Tell affected people plainly: what happened, what data, what you are doing, what they can do. For
   prayer requests and testimonies, consider a personal contact rather than a mass email.
5. Keep a written record of the incident, decisions and notifications.

## 6. Spam flood or abuse of forms

The forms already have rate limits, a honeypot and Turnstile. If spam still gets through:
1. Check Turnstile keys are set and **TURNSTILE_ENABLED** is on (`manage.py check --deploy` warns otherwise).
2. Lower limits temporarily in `.env`: `FORM_RATE=2/h`, restart.
3. **(server)** Add a Cloudflare WAF rule or "Under attack" mode.
4. Delete the spam items (Membership Administration: select → delete). Never click links in spam submissions.

## 7. The website is defaced or shows harmful content

1. If it is admin-edited content: unpublish it, then follow §1 for the account that changed it (audit log
   shows who).
2. If it is not in the admin (changed files/templates): treat as §3.

## 8. After every incident

Within two weeks: a short written review. What happened, how it was found, what worked, what will change
(a new rule, a training point, a code fix with a test). Update this document if a step was missing.

---

### Useful commands (technical lead)

```bash
docker compose ps                                     # what is running
docker compose logs --since 24h web worker            # application logs (PII is scrubbed)
docker compose exec web python manage.py check --deploy --settings=config.settings.prod
docker compose exec web python manage.py personal_data find --email someone@example.org
```
