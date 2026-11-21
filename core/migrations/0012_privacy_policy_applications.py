"""Privacy policy: how applications are kept (ministry decision 8).

Adds an "Applications" section before "How long we keep it". Nothing already written is changed: the section is
only inserted, and only once. If leadership has removed that heading, nothing is inserted and the admin guide asks
them to add the text themselves. The live periods are listed automatically under the policy.
"""

from django.db import migrations

ANCHOR = "## How long we keep it"
MARKER = "## Applications"
SECTION = """## Applications
This covers the membership, discipleship, partnership and finance-volunteer forms.
- While we consider your application, only the staff of the department concerned can see it. Applications from people under 18 are seen only by the head of that department and the Founder.
- If your application is successful, your details move into the ministry's records (for example the member register, a discipleship class or our partner list) and the application itself keeps only a reference to that record.
- If your application is not successful, we keep it for the period shown below, counted from the date of the decision, and then delete it automatically, including any documents you sent. Applications from people under 18 are deleted sooner. We keep only anonymous numbers (type of application, branch, month and outcome) for our reports.
- We keep an application longer only when the law requires it, for example during a legal dispute.
- You can ask us to delete your application sooner through the Contact page.

"""


def add_section(apps, schema_editor):  # type: ignore[no-untyped-def]
    Page = apps.get_model("core", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page is None or MARKER in page.body or ANCHOR not in page.body:
        return
    page.body = page.body.replace(ANCHOR, SECTION + ANCHOR, 1)
    page.save(update_fields=["body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("core", "0011_backfill_application_outcomes")]

    operations = [migrations.RunPython(add_section, migrations.RunPython.noop)]
