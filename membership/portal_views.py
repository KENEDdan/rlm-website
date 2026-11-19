"""Membership workflow screens: admission steps, attendance sheet, bulk messages."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from audit.models import AuditLog
from audit.services import log_event
from portal.access import BRANCH, HEAD, MEMBER, get_access, portal_view
from portal.views import post_action

from . import services
from .portal_config import DEPT, MemberResource, scoped_members


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["GET", "POST"])
def member_step(request: HttpRequest, pk: int, name: str) -> HttpResponse:
    access = get_access(request)
    resource, member = post_action(request, DEPT, "members", pk, "change")
    is_head = access.is_head(DEPT)
    if name not in services.available_transitions(member, is_head=is_head):
        raise PermissionDenied
    if request.method == "POST":
        try:
            services.transition(request, member, name, is_head=is_head, note=request.POST.get("note", ""))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, f"{services.LABELS[name]}: done.")
            return redirect(resource.url("detail", member))
    return render(
        request,
        "membership/step.html",
        {
            "department": DEPT,
            "member": member,
            "name": name,
            "label": services.LABELS[name],
            "resource": resource,
        },
    )


@never_cache
@portal_view(DEPT, level=BRANCH)
@require_http_methods(["GET", "POST"])
def attendance(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_access(request)
    resource, activity = post_action(request, DEPT, "activities", pk, "change")
    members = scoped_members(access).filter(status__in=MemberResource.model.CURRENT)
    if activity.branch_id:
        members = members.filter(branch_id=activity.branch_id)
    if request.method == "POST":
        present = {int(v) for v in request.POST.getlist("present") if v.isdigit()}
        count = services.record_attendance(request, activity, present, members)
        messages.success(request, f"Attendance saved for {count} member(s).")
        return redirect(resource.url("detail", activity))
    marked = set(activity.attendance.filter(present=True).values_list("member_id", flat=True))
    rows = [(m, m.pk in marked) for m in members.order_by("member_number")]
    return render(
        request,
        "membership/attendance.html",
        {"department": DEPT, "activity": activity, "rows": rows, "resource": resource},
    )


@never_cache
@portal_view(DEPT, level=HEAD)
@require_POST
def send(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_access(request)
    resource, message = post_action(request, DEPT, "messages", pk, "view")
    try:
        count = services.send_bulk_email(request, message, scoped_members(access))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Sending to {count} member(s).")
    return redirect(resource.url("detail", message))


@never_cache
@portal_view(DEPT, level=HEAD)
def whatsapp(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_access(request)
    resource, message = post_action(request, DEPT, "messages", pk, "view")
    links = services.whatsapp_links(message, scoped_members(access))
    log_event(AuditLog.Action.VIEW, request=request, obj=message, extra={"whatsapp_links": len(links)})
    return render(
        request,
        "membership/whatsapp.html",
        {"department": DEPT, "message": message, "links": links, "resource": resource},
    )
