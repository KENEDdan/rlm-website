"""One ledger (ministry decision 6): project budgets become Finance budget lines and recorded project costs become
Finance ledger entries tagged with the project. Nothing is lost and nothing is counted twice:

* a project with a budget gets a DRAFT budget line (Development department) for that amount, which Finance and the
  executive then approve like any other line;
* each old project expense becomes a DRAFT expenditure entry tagged with the project (its old voucher number kept
  in ``reference``). Finance checks it against the real books and submits it, or deletes it if it was already
  recorded in the ledger; nothing is posted automatically.
"""

import django.db.models.deletion
from django.db import migrations, models


def to_ledger(apps, schema_editor):  # type: ignore[no-untyped-def]
    Project = apps.get_model("development", "Project")
    ProjectExpense = apps.get_model("development", "ProjectExpense")
    BudgetLine = apps.get_model("finance", "BudgetLine")
    LedgerEntry = apps.get_model("finance", "LedgerEntry")
    FinancialYear = apps.get_model("finance", "FinancialYear")
    Department = apps.get_model("portal", "Department")
    dept = Department.objects.filter(code="development").first()
    if dept is None:
        return

    def fy(year):  # type: ignore[no-untyped-def]
        return FinancialYear.objects.get_or_create(year=year)[0]

    for project in Project.objects.all():
        if project.old_budget and project.budget_line_id is None:
            year = (project.start_date or project.created_at).year
            line = BudgetLine.objects.create(
                year=year,
                financial_year=fy(year),
                department=dept,
                branch_id=project.branch_id,
                category="construction",
                name=f"Project: {project.name}"[:120],
                amount=project.old_budget,
                status="draft",
                notes="Created from the project's budget when project costs moved into the Finance ledger.",
            )
            project.budget_line = line
            project.save(update_fields=["budget_line"])
        for expense in ProjectExpense.objects.filter(project=project):
            LedgerEntry.objects.create(
                kind="expense",
                status="draft",
                date=expense.date,
                financial_year=fy(expense.date.year),
                amount=expense.amount,
                currency=project.currency or "USD",
                category="construction",
                description=expense.description[:255],
                reference=(expense.reference or "")[:60],
                department=dept,
                branch_id=project.branch_id,
                budget_line_id=project.budget_line_id,
                project=project,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("development", "0001_initial"),
        ("finance", "0006_existing_budget_lines_approved"),
    ]

    operations = [
        migrations.RenameField(model_name="project", old_name="budget", new_name="old_budget"),
        migrations.AddField(
            model_name="project",
            name="budget_line",
            field=models.OneToOneField(
                blank=True,
                help_text=(
                    "The project's cost centre in the Finance budget. Its costs are the ledger entries tagged with "
                    "the project."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="project",
                to="finance.budgetline",
            ),
        ),
        migrations.RunPython(to_ledger, migrations.RunPython.noop),
        migrations.RemoveField(model_name="project", name="old_budget"),
        migrations.DeleteModel(name="ProjectExpense"),
    ]
