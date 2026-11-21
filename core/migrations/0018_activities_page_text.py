"""Page wording for the activities (replacing the programmes) and removal of the old static-hero text (the hero is
now edited in Hero settings, seeded from that text in 0017). Rows staff had edited are left alone."""

from django.db import migrations

OLD_TO_NEW = {
    "home_programmes": (
        {"label": "Home: programmes section", "heading": "Our programmes"},
        {
            "label": "Home: activities section",
            "heading": "Our activities",
            "intro": "Four ways we rebuild lives and revive a generation.",
        },
    ),
    "programs": (
        {"label": "Programmes page", "eyebrow": "Programmes"},
        {
            "label": "Activities page",
            "eyebrow": "Our activities",
            "intro": "Charitable and humanitarian services, evangelism and missions, discipleship and revival: "
            "find an activity near you and get involved.",
        },
    ),
}


def forward(apps, schema_editor):  # type: ignore[no-untyped-def]
    PageText = apps.get_model("core", "PageText")
    for key, (old, new) in OLD_TO_NEW.items():
        row = PageText.objects.filter(key=key).first()
        if row is None:
            continue
        row.label = new["label"]  # labels are not editable by staff
        if all(getattr(row, k) == v for k, v in old.items() if k != "label"):
            for k, v in new.items():
                setattr(row, k, v)
        row.save()
    PageText.objects.filter(key="home_hero").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0017_hero_settings_seed")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
