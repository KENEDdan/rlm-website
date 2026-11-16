"""Seed SiteSettings (no contacts) and DRAFT privacy policy / terms that leadership must review."""

from django.db import migrations

VISION = "A generation restored to God, rebuilt in faith and revived to transform their communities."
MISSION = (
    "To rebuild lives through the Gospel of Jesus Christ by revival, discipleship, evangelism and "
    "leadership development, starting in South Sudan and reaching the nations."
)
ABOUT_INTRO = (
    "Rebuilding Lives Ministry (RLM) is a Christian ministry raising a generation that loves God, "
    "knows His Word and serves their communities. From our branches in Juba and Yei we gather young people "
    "and families for worship, prayer, teaching and outreach."
)
ABOUT_BODY = (
    "Our name comes from Acts 15:16, where God promises to rebuild what has fallen down and restore it. "
    "We believe that no life is too broken for God to rebuild.\n\n"
    "Through revival conferences, discipleship, evangelism and missions, and youth and leadership development, "
    "we walk with people as their faith grows and as they discover their calling.\n\n"
    "This text is a placeholder. Leadership will replace it with the ministry's official story."
)

PRIVACY = """## Draft: to be reviewed by ministry leadership before launch

## Who we are
Rebuilding Lives Ministry ("RLM", "we") runs this website. You can reach us through the Contact page.

## What we collect and why
When you use a form on this site we collect only what the form asks for:
- Prayer requests: your request and, only if you choose, your name and contact details, so that we can pray and, if you ask, contact you.
- Volunteer applications: your contact details, location, church affiliation, interests, experience and (optionally) testimony, so that we can arrange volunteering.
- Event registrations: your name, contact details and number of attendees, so that we can plan the event and contact you about it.
- Contact and partnership messages: your details and message, so that we can reply.
- Newsletter: your email address (and optionally first name), only after you confirm by clicking the link we send you.
- Giving pledges: the amount, category and, if you choose, your name and email for a receipt. We never collect or store card numbers.

## How we protect it
Personal details and prayer requests are encrypted in our database. Only named staff members with a need to know can read them, every staff account uses two-factor authentication, and access is logged.

## How long we keep it
We keep submissions only as long as needed and delete them automatically after the retention periods set by the ministry (for example, prayer requests after 12 months). Financial records are kept as long as the law requires.

## Sharing
We do not sell or rent your information. We share it only with services that help us run the site (for example, our email provider), under agreements to protect it, or where the law requires.

## Cookies and analytics
We use only essential cookies (for security and forms). If analytics are enabled, they are privacy-friendly and cookieless, and load only after you agree.

## Your rights
You can ask us to show you, correct, export or delete the information we hold about you by contacting us. You can unsubscribe from emails at any time using the link in every email.

## Changes
We will update this page if our practices change and show the date of the last review.
"""

TERMS = """## Draft: to be reviewed by ministry leadership before launch

## Using this website
This website provides information about Rebuilding Lives Ministry and ways to get involved. Please use it respectfully and lawfully.

## Content
Sermons, devotionals, photos and other content belong to the ministry or their owners. You may share links and short quotations with credit. Please ask before republishing.

## Submissions
When you send us a form, please give accurate information. Do not submit anything that is unlawful or that infringes the rights of others.

## Giving
Gifts are voluntary. Bank transfer details are shown on the Give page, and our finance team confirms gifts before issuing receipts. Online payments, when available, are processed by a secure payment provider; we never see or store your card details.

## Links
We are not responsible for the content of external websites we link to.

## Contact
Questions about these terms can be sent through the Contact page.
"""


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    SiteSettings = apps.get_model("core", "SiteSettings")
    Page = apps.get_model("core", "Page")
    SiteSettings.objects.get_or_create(
        pk=1,
        defaults={"vision": VISION, "mission": MISSION, "about_intro": ABOUT_INTRO, "about_body": ABOUT_BODY},
    )
    Page.objects.get_or_create(slug="privacy", defaults={"title": "Privacy policy", "body": PRIVACY, "is_published": True})
    Page.objects.get_or_create(slug="terms", defaults={"title": "Terms of use", "body": TERMS, "is_published": True})


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
