"""Budget lines created before executive approval existed (decision 3) count as approved, so nothing that was
budgeted becomes 'unbudgeted' overnight. New lines start as drafts and need executive approval."""

from django.db import migrations


def approve_existing(apps, schema_editor):  # type: ignore[no-untyped-def]
    BudgetLine = apps.get_model("finance", "BudgetLine")
    BudgetLine.objects.filter(status="draft").update(status="approved")


class Migration(migrations.Migration):
    dependencies = [("finance", "0005_remove_financesettings_approval_threshold_and_more")]
    operations = [migrations.RunPython(approve_existing, migrations.RunPython.noop)]
