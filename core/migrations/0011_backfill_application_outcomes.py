"""Existing applications get an outcome from their status (ministry decision 8). The retention clock of an
already-decided application starts at its recorded decision date, or its last change when none was recorded.
Partnership registrations stay pending until Finance marks them successful or unsuccessful."""

from django.db import migrations

STATUSES = {
    ("membership", "Member"): (("rejected",), ("approved", "orientation", "integration", "active", "inactive")),
    ("discipleship", "Registration"): (("declined",), ("enrolled",)),
    ("finance", "FinanceVolunteer"): (("declined",), ("approved",)),
}
REFERENCE = {"Member": "Member register", "FinanceVolunteer": "Vetted finance-volunteer list"}


def backfill(apps, schema_editor):  # type: ignore[no-untyped-def]
    for (app, name), (unsuccessful, successful) in STATUSES.items():
        model = apps.get_model(app, name)
        has_decided = any(f.name == "decided_at" for f in model._meta.fields)
        for obj in model.objects.filter(status__in=unsuccessful + successful):
            obj.outcome = "unsuccessful" if obj.status in unsuccessful else "successful"
            obj.outcome_at = (getattr(obj, "decided_at", None) if has_decided else None) or obj.updated_at
            if obj.outcome == "successful":
                if name == "Registration":
                    disciple = getattr(obj, "disciple", None)
                    obj.record_reference = f"Disciple #{disciple.pk}" if disciple else ""
                else:
                    obj.record_reference = REFERENCE[name]
            obj.save(update_fields=["outcome", "outcome_at", "record_reference"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_application_retention"),
        ("membership", "0002_application_retention"),
        ("discipleship", "0003_application_retention"),
        ("finance", "0007_application_retention"),
        ("giving", "0005_application_retention"),
    ]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
