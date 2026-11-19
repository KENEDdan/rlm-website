"""Discipleship workflow screens: registrations, follow-up steps, enrolment, class attendance."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from audit.models import AuditLog
from audit.services import log_event
from portal.access import BRANCH, MEMBER, get_access, portal_view
from portal.views import post_action

from . import services
from .models import Cohort, Enrollment, SessionAttendance
from .portal_config import DEPT, CohortResource, DiscipleResource


def _fail(request: HttpRequest, exc: ValidationError) -> None:
    messages.error(request, " ".join(exc.messages))


def _cohort(request: HttpRequest) -> Cohort | None:
    raw = request.POST.get("cohort", "")
    if not raw.isdigit():
        return None
    return CohortResource().get_queryset(get_access(request)).filter(pk=int(raw)).first()


def _cohort_choices(request: HttpRequest):  # type: ignore[no-untyped-def]
    return CohortResource().get_queryset(get_access(request)).exclude(status=Cohort.Status.COMPLETED)


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_POST
def registration_step(request: HttpRequest, pk: int, step: str) -> HttpResponse:
    resource, reg = post_action(request, DEPT, "registrations", pk, "change")
    try:
        services.set_registration_status(request, reg, step)
    except ValidationError as exc:
        _fail(request, exc)
    return redirect(resource.url("detail", reg))


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["GET", "POST"])
def registration_enroll(request: HttpRequest, pk: int) -> HttpResponse:
    resource, reg = post_action(request, DEPT, "registrations", pk, "change")
    if request.method == "POST":
        try:
            disciple = services.enroll_registration(request, reg, _cohort(request))
        except ValidationError as exc:
            _fail(request, exc)
            return redirect(resource.url("detail", reg))
        messages.success(request, "Enrolled.")
        return redirect(DiscipleResource().url("detail", disciple))
    return render(
        request,
        "discipleship/enroll.html",
        {"department": DEPT, "obj": reg, "slug": "registrations", "cohorts": _cohort_choices(request)},
    )


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["GET", "POST"])
def follow_up_step(request: HttpRequest, pk: int, step: str) -> HttpResponse:
    resource, follow = post_action(request, DEPT, "follow-ups", pk, "change")
    if step not in services.FOLLOW_UP_STEPS:
        raise Http404
    if request.method == "GET":
        if step != "enroll":
            return redirect(resource.url("detail", follow))
        return render(
            request,
            "discipleship/enroll.html",
            {"department": DEPT, "obj": follow, "slug": "follow-ups", "cohorts": _cohort_choices(request)},
        )
    try:
        services.follow_up_step(request, follow, step, _cohort(request) if step == "enroll" else None)
    except ValidationError as exc:
        _fail(request, exc)
    else:
        messages.success(request, services.STEP_LABELS[step] + ": done.")
    return redirect(resource.url("detail", follow))


@never_cache
@portal_view(DEPT, level=BRANCH)
@require_http_methods(["GET", "POST"])
def attendance(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_access(request)
    resource, session = post_action(request, DEPT, "sessions", pk, "change")
    enrolled = Enrollment.objects.filter(
        cohort=session.cohort, status=Enrollment.Status.ENROLLED
    ).select_related("disciple")
    if not access.is_head(DEPT):
        enrolled = enrolled.exclude(disciple__is_minor=True)
    disciples = [e.disciple for e in enrolled]
    if request.method == "POST":
        present = {int(v) for v in request.POST.getlist("present") if v.isdigit()}
        with transaction.atomic():
            for disciple in disciples:
                SessionAttendance.objects.update_or_create(
                    session=session, disciple=disciple, defaults={"present": disciple.pk in present}
                )
            log_event(
                AuditLog.Action.CHANGE,
                request=request,
                obj=session,
                extra={"attendance_rows": len(disciples)},
            )
        messages.success(request, f"Attendance saved for {len(disciples)} disciple(s).")
        return redirect(resource.url("detail", session))
    marked = set(session.attendance.filter(present=True).values_list("disciple_id", flat=True))
    return render(
        request,
        "discipleship/attendance.html",
        {"department": DEPT, "session": session, "rows": [(d, d.pk in marked) for d in disciples]},
    )
