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
4. **Preserve evidence:** export the audit log view (Founder: **Audit log**, filter by date or person) and
   keep server logs. Do not "clean up" first.

---

## 1. A staff account may be compromised

*Signs: an unknown sign-in in the audit log, changes nobody made, a phishing email someone answered, a
password reused elsewhere that leaked.*

1. Founder: **Users → the person → untick Active → Save.** This blocks new sign-ins immediately.
2. Same screen: action **"Reset two-factor"** on that user.
3. Sign everyone out by restarting with a new `DJANGO_SECRET_KEY` if the attacker may have a session
   (see `docs/BACKUP_RESTORE.md` §3 last paragraph).
4. **Audit log → filter by that person**: list what they viewed, exported (`export`), changed or deleted
   since the suspected time. Exports of prayer requests, volunteers or donors are a **data breach** (§5).
5. Undo unauthorised content changes (check news, giving settings, leaders, pages, social links).
6. **Check Giving settings** bank/mobile-money details against the bank, by phone (§4).
7. Re-enable the person only after they set a **new unique password** with the Founder present and
   re-enrol their authenticator.

**If the Founder's account is compromised:** the technical lead disables it from the command line:
`docker compose exec web python manage.py shell -c "from accounts.models import User; User.objects.filter(email='FOUNDER_EMAIL').update(is_active=False)"`
then follows the same steps and creates a fresh Founder account with `manage.py create_founder` (HANDOVER §2).

## 2. A phone with the authenticator app is lost or stolen

Founder: **Users → the person → "Reset two-factor"**. The person signs in and scans a new QR code. If they
also suspect the password is known, change it at the same time (§1 step 7).

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
4. Delete the spam items (Secretary: select → delete). Never click links in spam submissions.

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
