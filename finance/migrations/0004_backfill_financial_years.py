"""Create a FinancialYear for every year already used and link existing budget lines and ledger entries."""

from django.db import migrations


def backfill(apps, schema_editor):  # type: ignore[no-untyped-def]
    FinancialYear = apps.get_model("finance", "FinancialYear")
    BudgetLine = apps.get_model("finance", "BudgetLine")
    LedgerEntry = apps.get_model("finance", "LedgerEntry")
    years = set(BudgetLine.objects.values_list("year", flat=True))
    years |= {d.year for d in LedgerEntry.objects.values_list("date", flat=True)}
    for year in years:
        fy, _ = FinancialYear.objects.get_or_create(year=year)
        BudgetLine.objects.filter(year=year).update(financial_year=fy)
        # Historical models have no immutability guard; this only links the year.
        LedgerEntry.objects.filter(date__year=year).update(financial_year=fy)


class Migration(migrations.Migration):
    dependencies = [("finance", "0003_financial_year")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
