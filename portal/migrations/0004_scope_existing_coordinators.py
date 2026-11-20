"""Keep today's behaviour after scope moved onto each role assignment (DECISIONS D-026).

Before, a Branch Coordinator who also belonged to a department was limited to their branch in every department.
Their existing department assignments therefore become single-branch assignments for that branch; everyone else
keeps "all branches".
"""

from django.db import migrations


def scope(apps, schema_editor):  # type: ignore[no-untyped-def]
    Membership = apps.get_model("portal", "DepartmentMembership")
    Group = apps.get_model("auth", "Group")
    coordinators = Group.objects.filter(name="Branch Coordinator").first()
    if coordinators is None:
        return
    for user in coordinators.user_set.filter(branch__isnull=False, is_superuser=False):
        Membership.objects.filter(user=user, branch__isnull=True).update(branch_id=user.branch_id)


class Migration(migrations.Migration):
    dependencies = [("portal", "0003_membership_branch_scope")]
    operations = [migrations.RunPython(scope, migrations.RunPython.noop)]
