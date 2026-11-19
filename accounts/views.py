from __future__ import annotations

import base64
import io
from typing import Any
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST
from django_otp import login as otp_login

from audit.models import AuditLog
from audit.services import log_event
from core.ratelimit import login_ratelimit

from . import twofactor
from .forms import ChoosePasswordForm, OTPForm, StaffLoginForm

NEXT_KEY = "2fa_next"
BACKUP_CODES_KEY = "backup_codes_once"


def admin_home() -> str:
    """Where staff land after signing in: the staff portal (it sends each person to their own dashboard)."""
    return "/" + settings.PORTAL_URL


def safe_next(request: HttpRequest, candidate: str | None) -> str:
    """Only allow same-host relative redirects (prevents open redirects)."""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return admin_home()


def _complete_login(request: HttpRequest, user: Any, backend: str, device: Any) -> str:
    nxt = request.session.get(NEXT_KEY)
    twofactor.clear_pending(request)
    login(request, user, backend=backend)  # rotates the session key
    otp_login(request, device)
    log_event(AuditLog.Action.LOGIN, request=request, user=user, extra={"method": device.__class__.__name__})
    return safe_next(request, nxt)


@sensitive_post_parameters("password")
@never_cache
@csrf_protect
@login_ratelimit
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated and request.user.is_verified():
        return redirect(safe_next(request, request.GET.get("next")))
    form = StaffLoginForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        user = form.user
        twofactor.start_pending(request, user, user.backend)
        request.session[NEXT_KEY] = safe_next(request, request.GET.get("next"))
        if twofactor.confirmed_totp(user):
            return redirect("accounts:verify")
        return redirect("accounts:setup")
    return render(request, "accounts/login.html", {"form": form})


@sensitive_post_parameters("code")
@never_cache
@csrf_protect
@login_ratelimit
@require_http_methods(["GET", "POST"])
def verify_view(request: HttpRequest) -> HttpResponse:
    user, backend = twofactor.get_pending_user(request)
    if user is None:
        messages.error(request, "Your sign-in expired. Please start again.")
        return redirect("accounts:login")
    if not twofactor.confirmed_totp(user):
        return redirect("accounts:setup")
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        device = twofactor.verify_code(user, form.cleaned_data["code"])
        if device is not None:
            return redirect(_complete_login(request, user, backend, device))
        attempts = twofactor.record_failed_attempt(request)
        log_event(AuditLog.Action.TWO_FACTOR_FAILED, request=request, user=user, extra={"attempt": attempts})
        form.add_error("code", "That code is not valid.")
    return render(request, "accounts/verify.html", {"form": form})


def _qr_svg_data_uri(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


@sensitive_post_parameters("code")
@never_cache
@csrf_protect
@login_ratelimit
@require_http_methods(["GET", "POST"])
def setup_view(request: HttpRequest) -> HttpResponse:
    """First sign-in: enrol an authenticator app. Staff cannot skip this step."""
    user, backend = twofactor.get_pending_user(request)
    if user is None:
        messages.error(request, "Your sign-in expired. Please start again.")
        return redirect("accounts:login")
    if twofactor.confirmed_totp(user):
        return redirect("accounts:verify")
    device = twofactor.get_or_create_unconfirmed_totp(user)
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"].strip()
        if code.isdigit() and device.verify_token(code):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            codes = twofactor.regenerate_backup_codes(user)
            log_event(AuditLog.Action.TWO_FACTOR_SETUP, request=request, user=user)
            _complete_login(request, user, backend, device)
            request.session[BACKUP_CODES_KEY] = codes
            return redirect("accounts:backup_codes")
        twofactor.record_failed_attempt(request)
        form.add_error("code", "That code is not valid. Check the time on your phone and try again.")
    issuer = settings.OTP_TOTP_ISSUER
    secret_b32 = base64.b32encode(device.bin_key).decode().rstrip("=")
    uri = (
        f"otpauth://totp/{quote(issuer)}:{quote(user.email)}"
        f"?secret={secret_b32}&issuer={quote(issuer)}&digits={device.digits}&period={device.step}"
    )
    context = {"form": form, "qr_data_uri": _qr_svg_data_uri(uri), "secret": secret_b32}
    return render(request, "accounts/setup.html", context)


@never_cache
def backup_codes_view(request: HttpRequest) -> HttpResponse:
    if not (request.user.is_authenticated and request.user.is_verified()):
        return redirect("accounts:login")
    codes = request.session.pop(BACKUP_CODES_KEY, None)
    if not codes:
        return redirect(admin_home())
    return render(request, "accounts/backup_codes.html", {"codes": codes, "admin_home": admin_home()})


@require_POST
@csrf_protect
def regenerate_backup_codes_view(request: HttpRequest) -> HttpResponse:
    if not (request.user.is_authenticated and request.user.is_verified()):
        return redirect("accounts:login")
    request.session[BACKUP_CODES_KEY] = twofactor.regenerate_backup_codes(request.user)
    log_event(AuditLog.Action.TWO_FACTOR_SETUP, request=request, extra={"backup_codes": "regenerated"})
    return redirect("accounts:backup_codes")


@require_POST
@csrf_protect
def logout_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        log_event(AuditLog.Action.LOGOUT, request=request)
    logout(request)
    return redirect("accounts:login")


INVALID_INVITE = (
    "This link is not valid. It may have expired, been replaced by a newer one or already been used. "
    "Ask the Super Admin to send a new one."
)


@sensitive_post_parameters("password1", "password2")
@never_cache
@csrf_protect
@login_ratelimit
@require_http_methods(["GET", "POST"])
def accept_invite_view(request: HttpRequest, token: str) -> HttpResponse:
    """Single-use, expiring link: choose a password, then 2FA enrolment is forced before anything else.

    Every failure (unknown, expired, used, revoked) gets the same response, so links cannot be probed.
    """
    from .services import AccountError, accept_invitation, find_invitation

    invitation = find_invitation(token)
    if invitation is None:
        log_event(AuditLog.Action.INVITE_REJECTED, request=request)
        return render(request, "accounts/invite_invalid.html", {"message": INVALID_INVITE}, status=404)
    form = ChoosePasswordForm(request.POST or None, user=invitation.user)
    if request.method == "POST" and form.is_valid():
        try:
            user = accept_invitation(request, invitation, form.cleaned_data["password1"])
        except AccountError:
            return render(request, "accounts/invite_invalid.html", {"message": INVALID_INVITE}, status=404)
        if request.user.is_authenticated:
            logout(request)
        twofactor.start_pending(request, user, "django.contrib.auth.backends.ModelBackend")
        request.session[NEXT_KEY] = admin_home()
        messages.success(request, "Password saved. Now set up two-step sign-in.")
        if twofactor.confirmed_totp(user):
            return redirect("accounts:verify")
        return redirect("accounts:setup")
    return render(request, "accounts/invite_accept.html", {"form": form, "invitation": invitation})
