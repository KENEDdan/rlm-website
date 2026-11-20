"""Monthly performance targets (ministry decision 4).

Existing indicators keep their values. Their per-period target becomes an annual target for the year they were
created in (monthly x12, quarterly x4 for counts and money; percentages keep their level), they become monthly
indicators, and they get a category from their department (Logistics, which has no category of its own, maps to
Development; leadership can change it).
"""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

CATEGORY = {
    "membership": "membership",
    "finance": "finance",
    "logistics": "development",
    "media": "media",
    "missions": "missions",
    "discipleship": "discipleship",
    "development": "development",
}


def convert(apps, schema_editor):  # type: ignore[no-untyped-def]
    Indicator = apps.get_model("portal", "Indicator")
    for indicator in Indicator.objects.select_related("department"):
        factor = {"monthly": 12, "quarterly": 4, "annual": 1}.get(indicator.period, 12)
        if indicator.unit != "percent":
            indicator.annual_target = indicator.annual_target * factor
        indicator.year = indicator.created_at.year
        indicator.category = CATEGORY.get(indicator.department.code, "development")
        indicator.period = "monthly"
        indicator.save(update_fields=["annual_target", "year", "category", "period"])


class Migration(migrations.Migration):
    dependencies = [
        ("branches", "0001_initial"),
        ("portal", "0004_scope_existing_coordinators"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="indicator", name="unique_indicator_name"),
        migrations.RenameField(model_name="indicator", old_name="target", new_name="annual_target"),
        migrations.AddField(
            model_name="indicator",
            name="category",
            field=models.CharField(
                choices=[
                    ("evangelism", "Evangelism"),
                    ("discipleship", "Discipleship"),
                    ("youth", "Youth fellowships"),
                    ("membership", "Membership"),
                    ("partnerships", "Partnerships"),
                    ("missions", "Missions"),
                    ("finance", "Finance"),
                    ("development", "Development"),
                    ("media", "Media"),
                    ("prayer", "Prayer"),
                ],
                db_index=True,
                default="development",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="indicator",
            name="year",
            field=models.PositiveSmallIntegerField(
                db_index=True,
                default=2026,
                help_text="January to December (ministry decision 2).",
                verbose_name="financial year",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="indicator",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                help_text="Leave empty for a ministry-wide target.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="indicators",
                to="branches.branch",
            ),
        ),
        migrations.AddField(
            model_name="indicator",
            name="is_demo",
            field=models.BooleanField(
                default=False,
                editable=False,
                help_text="Sample target created for demonstration; never a real target.",
            ),
        ),
        migrations.RunPython(convert, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="indicator",
            name="period",
            field=models.CharField(
                choices=[("monthly", "Monthly"), ("quarterly", "Quarterly"), ("annual", "Annual")],
                default="monthly",
                editable=False,
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="indicator",
            name="department",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="indicators",
                to="portal.department",
                verbose_name="owner department",
            ),
        ),
        migrations.AlterModelOptions(name="indicator", options={"ordering": ["category", "department__order", "name"]}),
        migrations.AddConstraint(
            model_name="indicator",
            constraint=models.UniqueConstraint(
                fields=("department", "name", "year", "branch"),
                name="unique_indicator_per_year_branch",
                nulls_distinct=False,
            ),
        ),
        migrations.CreateModel(
            name="MonthlyTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "month",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(12),
                        ]
                    ),
                ),
                ("target", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "indicator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="monthly_targets",
                        to="portal.indicator",
                    ),
                ),
            ],
            options={"ordering": ["month"]},
        ),
        migrations.AddConstraint(
            model_name="monthlytarget",
            constraint=models.UniqueConstraint(fields=("indicator", "month"), name="unique_month_target"),
        ),
        migrations.CreateModel(
            name="TargetChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "month",
                    models.PositiveSmallIntegerField(blank=True, help_text="Empty = the annual target.", null=True),
                ),
                ("old_value", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("new_value", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "indicator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="target_changes",
                        to="portal.indicator",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
