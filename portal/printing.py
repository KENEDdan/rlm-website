"""Printable reports (ministry decision 7).

Every report prints from a STANDALONE template that extends ``print/base.html`` (no portal chrome, no
JavaScript needed to lay it out), so the same templates can later be fed to a server-side PDF renderer.
Each print carries: logo and ministry name, report title, department, branch or "All branches", period and
financial year, generated date/time and by whom, page numbers, a confidentiality footer for sensitive reports
and an approval section (Prepared / Reviewed / Approved by: name, signature, date).

Opening a print view is audit-logged (``AuditLog.Action.PRINT``). Printing a sensitive list needs the same
permission as exporting it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

CONFIDENTIAL = (
    "CONFIDENTIAL: contains personal or financial information of the ministry. For authorised staff only. "
    "Do not copy, forward or leave unattended; shred when no longer needed."
)
INTERNAL = "Internal document of the ministry. Do not forward outside the ministry."


def print_context(
    request: HttpRequest,
    *,
    title: str,
    department: str = "",
    branch: str = "",
    start: dt.date | None = None,
    end: dt.date | None = None,
    period_label: str = "",
    fy: int | None = None,
    sensitive: bool = False,
    back_url: str = "",
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Header/footer data for ``print/base.html``; also writes the PRINT audit entry."""
    user = request.user
    now = timezone.localtime()
    if start and end and not period_label:
        period_label = f"{start:%d %b %Y} to {end:%d %b %Y}"
    log_event(
        AuditLog.Action.PRINT,
        request=request,
        extra={
            "report": title,
            "department": department,
            "branch": branch or "all",
            "period": period_label,
            **(audit or {}),
        },
    )
    return {
        "report": {
            "title": title,
            "department": department or "Ministry-wide",
            "branch": branch or "All branches",
            "period": period_label or "Not limited to a period",
            "fy": fy or (end.year if end else now.year),
            "generated_at": now,
            "generated_by": (user.get_full_name() or user.get_username()) if user.is_authenticated else "",
            "sensitive": sensitive,
            "footer": CONFIDENTIAL if sensitive else INTERNAL,
            "back_url": back_url,
        }
    }
