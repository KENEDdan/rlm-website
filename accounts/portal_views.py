"""Super Admin-only account screens in the staff portal (create/invite, roles, lifecycle, review, audit)."""

from __future__ import annotations

import csv
from functools import wraps
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_ratelimit.decorators import ratelimit

from audit.models import AuditLog
from audit.services import log_event
from core.admin_mixins import csv_safe
from core.ratelimit import login_ratelimit
from portal.access import portal_view

from . import reauth, services, twofactor
from .forms import ReauthForm
from .models import Invitation, User
from .portal_forms import InviteForm, RolesForm


def _invite_rate(group: str, request: HttpRequest) -> str:
    from django.conf import settings

    return settings.INVITE_RATE


def needs_reauth(view: Any) -> Any:
    """Send the Super Admin through password + 2FA again before the screen (and its POST) is usable."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not reauth.is_fresh(request):
            target = (
                request.get_full_path() if request.method == "GET" else request.META.get("HTTP_REFERER", "")
            )
            if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
                target = reverse("portal:users")
            return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': target})}")
        try:
            return view(request, *args, **kwargs)
        except reauth.ReauthRequired:
            return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': reverse('portal:users')})}")

    return wrapper


def _user(pk: int) -> User:
    return get_object_or_404(User._base_manager, pk=pk)


def _has_2fa(user: User) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def _row(user: User) -> dict[str, Any]:
    memberships = [
        f"{m.department.name}{' (head)' if m.is_head else ''}"
        for m in user.memberships.select_related("department")
    ]
    roles = list(user.groups.values_list("name", flat=True))
    if user.deleted_at:
        status = "Deleted"
    elif not user.is_active and not user.has_usable_password():
        status = "Invited (not accepted)"
    elif not user.is_active:
        status = "Deactivated"
    else:
        status = "Active"
    return {
        "user": user,
        "status": status,
        "super_admin": user.is_superuser,
        "departments": memberships,
        "roles": roles,
        "branch": user.branch,
        "two_factor": _has_2fa(user),
        "last_login": user.last_login,
        "dormant": user.dormant_flagged_at is not None,
    }


# ------------------------------------------------------------------------------------------- re-auth
@sensitive_post_parameters("password", "code")
@never_cache
@portal_view(super_admin=True)
@login_ratelimit
@require_http_methods(["GET", "POST"])
def reauth_view(request: HttpRequest) -> HttpResponse:
    nxt = request.GET.get("next") or reverse("portal:users")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = reverse("portal:users")
    form = ReauthForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        password_ok = user.check_password(form.cleaned_data["password"])
        device = twofactor.verify_code(user, form.cleaned_data["code"]) if password_ok else None
        if password_ok and device is not None:
            reauth.mark_fresh(request)
            log_event(AuditLog.Action.REAUTH, request=request)
            return redirect(nxt)
        log_event(AuditLog.Action.REAUTH_FAILED, request=request)
        form.add_error(None, "The password or the code is not correct.")
    return render(request, "accounts/portal/reauth.html", {"form": form, "next": nxt})


# ------------------------------------------------------------------------------------------- list / detail
@never_cache
@portal_view(super_admin=True)
def users(request: HttpRequest) -> HttpResponse:
    qs = User._base_manager.order_by("deleted_at", "-is_active", "full_name", "email")
    status = request.GET.get("status", "")
    if status == "active":
        qs = qs.filter(is_active=True, deleted_at__isnull=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False, deleted_at__isnull=True)
    elif status == "deleted":
        qs = qs.filter(deleted_at__isnull=False)
    term = request.GET.get("q", "").strip()[:100]
    if term:
        qs = qs.filter(Q(full_name__icontains=term) | Q(email__icontains=term))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "accounts/portal/users.html",
        {"rows": [_row(u) for u in page.object_list], "page": page, "status": status, "q": term},
    )


@never_cache
@portal_view(super_admin=True)
def user_detail(request: HttpRequest, pk: int) -> HttpResponse:
    user = _user(pk)
    context = {
        "row": _row(user),
        "target": user,
        "invitations": Invitation.objects.filter(user=user)[:10],
        "is_self": user.pk == request.user.pk,
        "history": AuditLog.objects.filter(
            Q(app_label="accounts", model="user", object_id=str(user.pk)) | Q(extra__target_user_id=user.pk)
        )[:30],
    }
    return render(request, "accounts/portal/user_detail.html", context)


# ------------------------------------------------------------------------------------------- invite / roles
@sensitive_post_parameters()
@never_cache
@portal_view(super_admin=True)
@needs_reauth
@ratelimit(key="user", rate=_invite_rate, method="POST", block=True)
@require_http_methods(["GET", "POST"])
def user_invite(request: HttpRequest) -> HttpResponse:
    form = InviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = services.invite_user(
                request,
                email=form.cleaned_data["email"],
                full_name=form.cleaned_data["full_name"],
                spec=form.spec(),
            )
        except services.AccountError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Invitation sent. The link works once and expires automatically.")
            return redirect("portal:user_detail", pk=user.pk)
    return render(request, "accounts/portal/user_form.html", {"form": form, "title": "Invite a staff member"})


@never_cache
@portal_view(super_admin=True)
@needs_reauth
@require_http_methods(["GET", "POST"])
def user_roles(request: HttpRequest, pk: int) -> HttpResponse:
    user = _user(pk)
    if user.pk == request.user.pk:
        raise PermissionDenied  # nobody edits their own roles
    form = RolesForm(request.POST or None, initial=RolesForm.initial_from(services.current_spec(user)))
    if request.method == "POST" and form.is_valid():
        try:
            services.change_roles(request, user, form.spec())
        except services.AccountError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Roles updated.")
            return redirect("portal:user_detail", pk=user.pk)
    return render(
        request,
        "accounts/portal/user_form.html",
        {"form": form, "title": f"Roles for {user}", "target": user},
    )


ACTIONS = {
    "deactivate": (services.deactivate, "Account deactivated and signed out everywhere."),
    "reactivate": (services.reactivate, "Account reactivated."),
    "reset_2fa": (
        services.reset_2fa,
        "Two-step sign-in reset. They will set it up again at their next sign-in.",
    ),
    "force_password_reset": (
        services.force_password_reset,
        "Password invalidated and a single-use reset link was emailed.",
    ),
    "unlock": (services.unlock, "Sign-in lockout cleared."),
    "delete": (services.soft_delete, "Account deleted (kept in the audit history)."),
    "resend_invite": (services.resend_invitation, "A new invitation was sent; older links no longer work."),
    "revoke_invites": (services.revoke_invitations, "Open invitations revoked."),
}


@never_cache
@portal_view(super_admin=True)
@needs_reauth
@require_POST
def user_action(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    if action not in ACTIONS:
        raise Http404
    user = _user(pk)
    func, message = ACTIONS[action]
    try:
        func(request, user)
    except services.AccountError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, message)
    return redirect("portal:user_detail", pk=user.pk)


# ------------------------------------------------------------------------------------------- review / audit
@never_cache
@portal_view(super_admin=True)
def account_review(request: HttpRequest) -> HttpResponse:
    rows = [
        _row(u) for u in User._base_manager.filter(deleted_at__isnull=True).order_by("full_name", "email")
    ]
    if request.GET.get("format") == "csv":
        log_event(
            AuditLog.Action.EXPORT, request=request, model=User, extra={"count": len(rows), "review": True}
        )
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        writer = csv.writer(response)
        writer.writerow(
            [
                "Name",
                "Email",
                "Status",
                "Super Admin",
                "Departments",
                "Roles",
                "Branch",
                "2FA",
                "Last login",
                "Dormant",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    csv_safe(r["user"].full_name),
                    csv_safe(r["user"].email),
                    r["status"],
                    "yes" if r["super_admin"] else "no",
                    csv_safe("; ".join(r["departments"])),
                    csv_safe("; ".join(r["roles"])),
                    csv_safe(r["branch"] or ""),
                    "yes" if r["two_factor"] else "NO",
                    r["last_login"].isoformat() if r["last_login"] else "never",
                    "yes" if r["dormant"] else "",
                ]
            )
        response["Content-Disposition"] = f'attachment; filename="access-review-{timezone.now():%Y%m%d}.csv"'
        response["Cache-Control"] = "no-store"
        return response
    return render(request, "accounts/portal/review.html", {"rows": rows})


ACCOUNT_ACTIONS = [
    AuditLog.Action.ACCOUNT_CHANGE,
    AuditLog.Action.ACCOUNT_OUT_OF_BAND,
    AuditLog.Action.ACCOUNT_INTEGRITY,
    AuditLog.Action.INVITE_SENT,
    AuditLog.Action.INVITE_ACCEPTED,
    AuditLog.Action.INVITE_REVOKED,
    AuditLog.Action.INVITE_REJECTED,
    AuditLog.Action.REAUTH,
    AuditLog.Action.REAUTH_FAILED,
    AuditLog.Action.SESSIONS_KILLED,
    AuditLog.Action.ACCOUNT_UNLOCKED,
    AuditLog.Action.TWO_FACTOR_RESET,
    AuditLog.Action.TWO_FACTOR_SETUP,
    AuditLog.Action.LOGIN_FAILED,
]


@never_cache
@portal_view(super_admin=True)
def audit_trail(request: HttpRequest) -> HttpResponse:
    qs = AuditLog.objects.filter(action__in=ACCOUNT_ACTIONS)
    if request.GET.get("only") == "alerts":
        qs = qs.filter(action__in=[AuditLog.Action.ACCOUNT_OUT_OF_BAND, AuditLog.Action.ACCOUNT_INTEGRITY])
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "accounts/portal/audit.html", {"page": page, "only": request.GET.get("only", "")})
