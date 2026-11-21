"""Website Administration (Technical Team) in the staff portal: dashboard, Vision/Mission approvals, the home
hero (draft -> live preview -> publish -> revert) and the version history with one-click rollback.

Access: the Technical Team and the Super Admin only (``portal_view(technical=True)``); approvers (Super Admin,
Executive Director) also reach the Vision/Mission screens to decide changes. Nothing here touches finance,
donors, members, prayer or discipleship records, or accounts.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from accounts import reauth
from core import hero as hero_service
from core import site_health
from core import vision_mission as vm
from core.models import ContentChangeRequest, ContentVersion, HeroSettings, HeroSlide, SiteContent
from core.versioning import VERSIONED_MODELS, can_restore, restore

from .access import get_access, is_verified_staff, portal_view

S = ContentChangeRequest.Status


def _reauth_redirect(request: HttpRequest, back: str) -> HttpResponse:
    return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': back})}")


def _vm_access(view: Any) -> Any:
    """Technical Team, Super Admin and Vision/Mission approvers (Executive Director)."""

    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if is_verified_staff(request):
            access = get_access(request)
            if not (access.is_technical or vm.is_approver(request.user)):
                raise PermissionDenied
        return portal_view()(view)(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


# ---------------------------------------------------------------------------------------------- dashboard
@never_cache
@portal_view(technical=True)
def dashboard(request: HttpRequest) -> HttpResponse:
    draft, live = HeroSettings.draft(), HeroSettings.live()
    context = {
        "pages": site_health.pages_needing_update(),
        "open_changes": vm.open_changes(),
        "hero_draft_pending": draft.differs_from(live),
        "hidden_slides": HeroSlide.objects.filter(is_active=False).count(),
        "recent": ContentVersion.objects.select_related("content_type", "created_by")[:12],
        "problems": site_health.broken_links_and_files(),
        "storage": site_health.storage_usage(refresh=request.GET.get("refresh") == "storage"),
        "backup": site_health.backup_status(),
        "uptime": site_health.uptime(),
        "live_hero": live,
        "contrast_warning": hero_service.contrast_message(live),
    }
    return render(request, "portal/website/dashboard.html", context)


# ---------------------------------------------------------------------------------------------- vision & mission
class ChangeForm(forms.Form):
    field = forms.ChoiceField(choices=ContentChangeRequest.Field.choices, label="What to change")
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=2000, label="New wording")
    reason = forms.CharField(max_length=300, required=False, label="Why (optional)")


@never_cache
@_vm_access
def vision_mission(request: HttpRequest) -> HttpResponse:
    content = SiteContent.load()
    initial_field = (
        request.GET.get("field") if request.GET.get("field") in ("vision", "mission") else "vision"
    )
    context = {
        "content": content,
        "approval_required": vm.approval_required(),
        "open_changes": vm.open_changes(),
        "history": {f: list(vm.history(f)[:20]) for f in ("vision", "mission")},
        "can_draft": vm.can_draft(request.user),
        "is_approver": vm.is_approver(request.user),
        "form": ChangeForm(initial={"field": initial_field, "text": getattr(content, initial_field)}),
    }
    return render(request, "portal/website/vision_mission.html", context)


@never_cache
@_vm_access
@require_POST
def vm_create(request: HttpRequest) -> HttpResponse:
    form = ChangeForm(request.POST)
    if not form.is_valid():
        messages.error(
            request, "Check the form: " + "; ".join(e for errs in form.errors.values() for e in errs)
        )
        return redirect("portal:website:vision_mission")
    try:
        change = vm.create_draft(
            request, form.cleaned_data["field"], form.cleaned_data["text"], form.cleaned_data["reason"]
        )
    except vm.ChangeError as exc:
        messages.error(request, str(exc))
        return redirect("portal:website:vision_mission")
    messages.success(request, "Draft saved. Check the preview, then submit it.")
    return redirect("portal:website:vm_detail", pk=change.pk)


@never_cache
@_vm_access
@require_http_methods(["GET", "POST"])
def vm_detail(request: HttpRequest, pk: int) -> HttpResponse:
    change = get_object_or_404(ContentChangeRequest.objects.select_related("created_by", "decided_by"), pk=pk)
    back = reverse("portal:website:vm_detail", args=[pk])
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "edit":
                vm.update_draft(request, change, request.POST.get("text", ""), request.POST.get("reason", ""))
                messages.success(request, "Draft updated.")
            elif action == "submit":
                vm.submit(request, change)
                messages.success(request, "Submitted for approval.")
            elif action in ("approve", "reject"):
                if not reauth.is_fresh(request):
                    return _reauth_redirect(request, back)
                (vm.approve if action == "approve" else vm.reject)(
                    request, change, request.POST.get("note", "")
                )
                messages.success(
                    request, "Approved. It can now be published." if action == "approve" else "Not approved."
                )
            elif action == "withdraw":
                vm.withdraw(request, change)
                messages.success(request, "Withdrawn.")
            elif action == "publish":
                vm.publish(request, change)
                messages.success(
                    request, f"The new {change.get_field_display().lower()} is live on every page."
                )
                return redirect("portal:website:vision_mission")
            else:
                raise Http404
        except vm.ChangeError as exc:
            messages.error(request, str(exc))
        except reauth.ReauthRequired:
            return _reauth_redirect(request, back)
        return redirect(back)
    content = SiteContent.load()
    preview = {"vision": content.vision, "mission": content.mission, change.field: change.text}
    user = request.user
    context = {
        "change": change,
        "current": getattr(content, change.field),
        "preview": preview,
        "approval_required": vm.approval_required(),
        "is_author": change.created_by_id == user.pk,
        "is_approver": vm.is_approver(user),
        "can_publish": change.status == S.APPROVED
        or (not vm.approval_required() and change.status in (S.DRAFT, S.SUBMITTED)),
    }
    return render(request, "portal/website/vm_detail.html", context)


@never_cache
@_vm_access
@require_POST
def vm_rollback(request: HttpRequest, pk: int) -> HttpResponse:
    version = get_object_or_404(ContentChangeRequest, pk=pk, status=S.PUBLISHED)
    try:
        change = vm.rollback(request, version)
    except vm.ChangeError as exc:
        messages.error(request, str(exc))
        return redirect("portal:website:vision_mission")
    except reauth.ReauthRequired:
        return _reauth_redirect(request, reverse("portal:website:vision_mission"))
    if change.status == S.PUBLISHED:
        messages.success(request, "Rolled back: the earlier wording is live again.")
    else:
        messages.success(request, "Rollback submitted for approval by the Super Admin or Executive Director.")
    return redirect("portal:website:vision_mission")


# ---------------------------------------------------------------------------------------------- hero
HERO_FIELDS = [
    "title", "subtitle", "background_type", "image", "image_alt", "focal_x", "focal_y", "overlay_opacity", "video",
    "video_poster", "text_align", "text_tone", "button_text", "button_link", "button2_text", "button2_link",
    "show_scripture",
]  # fmt: skip


class HeroForm(forms.ModelForm):
    class Meta:
        model = HeroSettings
        fields = HERO_FIELDS
        widgets = {
            "focal_x": forms.NumberInput(attrs={"type": "range", "min": 0, "max": 100, "step": 1}),
            "focal_y": forms.NumberInput(attrs={"type": "range", "min": 0, "max": 100, "step": 1}),
            "overlay_opacity": forms.NumberInput(attrs={"type": "range", "min": 0, "max": 80, "step": 5}),
            "subtitle": forms.Textarea(attrs={"rows": 3}),
        }


@never_cache
@portal_view(technical=True)
@require_http_methods(["GET", "POST"])
def hero(request: HttpRequest) -> HttpResponse:
    from core.versioning import record

    if not request.user.has_perm("core.change_herosettings"):
        raise PermissionDenied
    draft, live = HeroSettings.draft(), HeroSettings.live()
    form = HeroForm(request.POST or None, request.FILES or None, instance=draft)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "publish":
            if not request.user.has_perm("core.change_herosettings"):
                raise PermissionDenied
            hero_service.publish(request)
            messages.success(request, "Published: visitors now see the new hero.")
            return redirect("portal:website:hero")
        if action == "revert":
            try:
                hero_service.revert(request)
                messages.success(request, "Reverted: the previous hero is live again.")
            except LookupError as exc:
                messages.error(request, str(exc))
            return redirect("portal:website:hero")
        if action == "discard":
            draft.copy_from(live)
            draft.save()
            record(draft, ContentVersion.Action.CHANGE, request=request, note="Draft reset to the live hero")
            messages.success(request, "Draft reset to what is live.")
            return redirect("portal:website:hero")
        if form.is_valid():
            draft = form.save()
            record(draft, ContentVersion.Action.CHANGE, request=request, note="Draft saved")
            messages.success(request, "Draft saved. Preview it, then publish.")
            warning = hero_service.contrast_message(draft)
            if warning:
                messages.warning(request, warning)
            return redirect("portal:website:hero")
        messages.error(request, "Please correct the highlighted fields.")
    context = {
        "form": form,
        "draft": draft,
        "live": live,
        "pending": draft.differs_from(live),
        "draft_warning": hero_service.contrast_message(draft),
        "can_revert": hero_service.previous_live_version(live) is not None,
        "slides_live": HeroSlide.objects.live().exists(),
    }
    return render(request, "portal/website/hero.html", context)


@never_cache
@portal_view(technical=True)
def hero_preview(request: HttpRequest) -> HttpResponse:
    """The draft hero (or one slide, even if switched off) on the real page layout. Not public."""
    slide_pk = request.GET.get("slide", "")
    item = get_object_or_404(HeroSlide, pk=int(slide_pk)) if slide_pk.isdigit() else HeroSettings.draft()
    response = render(
        request,
        "portal/website/hero_preview.html",
        {"hero": item, "warning": hero_service.contrast_message(item)},
    )
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ---------------------------------------------------------------------------------------------- versions
def _versioned_types() -> list[ContentType]:
    labels = [label.split(".") for label in VERSIONED_MODELS]
    return [ContentType.objects.get_by_natural_key(app, model) for app, model in labels]


@never_cache
@portal_view(technical=True)
def versions(request: HttpRequest) -> HttpResponse:
    qs = ContentVersion.objects.select_related("content_type", "created_by")
    types = _versioned_types()
    ct = request.GET.get("type", "")
    if ct.isdigit():
        qs = qs.filter(content_type_id=int(ct))
    obj_id = request.GET.get("object", "")
    if obj_id:
        qs = qs.filter(object_id=obj_id[:40])
    context = {"versions": qs[:100], "types": types, "type": ct, "object": obj_id}
    return render(request, "portal/website/versions.html", context)


@never_cache
@portal_view(technical=True)
@require_POST
def version_restore(request: HttpRequest, pk: int) -> HttpResponse:
    version = get_object_or_404(ContentVersion, pk=pk)
    if not can_restore(request.user, version):
        raise PermissionDenied
    obj = restore(version, request)
    messages.success(request, f"Restored '{obj}' to the version of {version.created_at:%d %b %Y %H:%M}.")
    return redirect(
        f"{reverse('portal:website:versions')}?{urlencode({'type': version.content_type_id, 'object': version.object_id})}"
    )
