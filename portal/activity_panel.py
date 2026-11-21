"""The "Our activities" panel of a department dashboard: the ministry activities routed to this department
(``programs.Activity.department``, set by the Super Admin) with their upcoming events, campaigns, cohorts and
targets. Counts respect the viewer's branch scope (D-026): a single-branch assignment counts only its branch.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from .access import Access


def activity_rows(access: Access, department: str) -> list[dict[str, Any]]:
    from programs.models import Activity

    restricted, branch_id = access.branch_scope(department)
    now = timezone.now()
    event_filter = Q(events__is_published=True, events__end__gte=now)
    campaign_filter = Q(campaigns__status__in=["planned", "approved", "in_progress"])
    cohort_filter = Q(cohorts__status__in=["planned", "running"])
    if restricted:
        event_filter &= Q(events__branch_id=branch_id)
        campaign_filter &= Q(campaigns__branch_id=branch_id)
        cohort_filter &= Q(cohorts__branch_id=branch_id)
    qs = (
        Activity.objects.filter(department__code=department)
        .select_related("category")
        .annotate(
            upcoming_events=Count("events", filter=event_filter, distinct=True),
            open_campaigns=Count("campaigns", filter=campaign_filter, distinct=True),
            open_cohorts=Count("cohorts", filter=cohort_filter, distinct=True),
            targets=Count("indicators", filter=Q(indicators__year=now.year), distinct=True),
        )
        .order_by("category__order", "order")
    )
    return [
        {
            "activity": a,
            "events": a.upcoming_events,
            "campaigns": a.open_campaigns if department == "missions" else None,
            "cohorts": a.open_cohorts if department == "discipleship" else None,
            "targets": a.targets,
        }
        for a in qs
    ]
