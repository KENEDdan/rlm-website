"""Replace the seeded DRAFT privacy policy with a fuller draft (third parties, cookies, legal basis, children,
transfers, complaints). Only applied if the page still holds the original untouched seed text, so anything
leadership has already edited is never overwritten. It stays marked Draft: leadership must review it.
"""

from django.db import migrations

ORIGINAL_MARKER = "We use only essential cookies (for security and forms)."

PRIVACY_V2 = """## Draft: to be reviewed by ministry leadership before launch
Items in [square brackets] must be completed or confirmed by leadership.

## Who we are
Rebuilding Lives Ministry ("RLM", "we") runs this website and decides how your information is used. [Legal name and registration details of the ministry.] You can reach us through the Contact page.

## What we collect and why
We collect only what each form asks for, and only for the purpose shown:
- Prayer requests: your request and, only if you choose, your name and contact details, so that we can pray and, if you ask, contact you.
- Volunteer applications: your contact details, location, church affiliation, interests, availability, experience and (optionally) testimony, so that we can arrange volunteering.
- Event registrations: your name, contact details and number of attendees, so that we can plan the event and contact you about it.
- Contact and partnership messages: your details and message, so that we can reply.
- Newsletter: your email address (and optionally your name), only after you confirm by clicking the link we send you.
- Giving pledges: the amount, category and, if you choose, your name, email and transfer reference for a receipt. We never collect or store card numbers or mobile-money PINs.
- Technical data: when you visit, your device's IP address and browser details reach our servers and security services so the site can work and be protected from attacks.

## Why we are allowed to use it (legal basis)
- Your consent, which you give on each form and can withdraw at any time.
- Our legitimate interest in running a safe website and replying to people who contact us.
- Legal obligations, for example keeping financial records.

## How we protect it
Personal details and prayer requests are encrypted in our database. Only named staff members who need them can read them, every staff account uses two-factor sign-in, and access is recorded in an audit log. Notification emails to our staff never contain what you wrote.

## Who else sees it
We do not sell, rent or trade your information. These services help us run the site and process data only on our instructions:
- [Hosting provider and country] runs the server.
- Cloudflare protects the site from attacks and checks that forms are sent by people, not robots (Turnstile).
- [Email provider] sends our emails (confirmations and receipts).
- YouTube shows videos, only after you press play (privacy-enhanced mode).
- [Payment provider], only if online giving is switched on; card details are entered on their page, never ours.
Some of these services may process data outside South Sudan; we choose providers that protect it.

## Children
Our forms are meant for adults. [Minimum age, e.g. 16.] Young people under that age should ask a parent or guardian to contact us for them. We only publish photos or testimonies of children with a parent's or guardian's written permission.

## Cookies and statistics
We use only cookies that are strictly necessary for the site to work; the exact list is below. If visitor statistics are switched on, they are privacy-friendly and cookieless, load only if you agree, and you can change your choice at any time with "Privacy choices" at the bottom of every page.

## How long we keep it
Submissions are deleted automatically after the periods listed below. Financial records are kept as long as the law requires.

## Your rights
You can ask us to show you, correct, export or delete the information we hold about you, or to stop using it, by writing to us through the Contact page. We will answer within [30] days. You can unsubscribe from emails at any time with the link in every email. If you are unhappy with how we handled your information, please tell us; you may also complain to a data protection authority where you live.

## Changes
We will update this page when our practices change and show the date of the last review at the top.
"""


def update_policy(apps, schema_editor):  # type: ignore[no-untyped-def]
    Page = apps.get_model("core", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page is not None and ORIGINAL_MARKER in page.body and page.body.lstrip().startswith("## Draft"):
        page.body = PRIVACY_V2
        page.save(update_fields=["body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("core", "0004_alter_page_options_page_order_page_show_in_footer_and_more")]

    operations = [migrations.RunPython(update_policy, migrations.RunPython.noop)]
