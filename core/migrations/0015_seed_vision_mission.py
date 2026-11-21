"""Seed the official Vision and Mission (received from the ministry, Nov 2026) VERBATIM.

The text below must not be reworded or re-punctuated; ``tests/test_vision_mission.py`` asserts it character for
character. Earlier (placeholder) wording, if any, is kept as the first entry of the version history so it can
be looked at, but the official text is what is published.
"""

from django.db import migrations
from django.utils import timezone

VISION = (
    "To see a generation of spiritually revived and purpose-driven young people in South Sudan and beyond, "
    "whose lives are rebuilt on biblical foundations and who influence their families, churches, communities "
    "and nations for the glory of God."
)
MISSION = (
    "To proclaim the Gospel of Jesus Christ, facilitate spiritual revival, disciple believers, develop godly "
    "leaders and equip young people to fulfil their God-given purpose through biblical teaching, evangelism, "
    "prayer and practical Christian service."
)


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    SiteContent = apps.get_model("core", "SiteContent")
    Change = apps.get_model("core", "ContentChangeRequest")
    content, _ = SiteContent.objects.get_or_create(pk=1)
    now = timezone.now()
    for field, text in (("vision", VISION), ("mission", MISSION)):
        previous = getattr(content, field) or ""
        Change.objects.create(
            field=field,
            text=text,
            previous_text=previous,
            reason="Official wording from the ministry (Nov 2026), seeded verbatim.",
            status="published",
            published_at=now,
            approval_was_required=False,
        )
        setattr(content, field, text)
    content.vision_mission_updated_at = now
    content.save()


def unseed(apps, schema_editor):  # type: ignore[no-untyped-def]
    apps.get_model("core", "ContentChangeRequest").objects.filter(
        reason__startswith="Official wording from the ministry"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0014_site_content_split")]
    operations = [migrations.RunPython(seed, unseed)]
