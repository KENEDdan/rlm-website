"""Part 5: ONE upload policy for every file field, and malicious samples it must refuse."""

from __future__ import annotations

import dataclasses
import io
import socketserver
import struct
import threading
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.test import override_settings

from core import upload_policy
from core.private_files import PrivateStorage
from core.upload_policy import (
    POLICIES,
    MissingPolicyValidator,
    PolicyValidator,
    validate_upload,
)
from core.uploads import PolicyFieldMixin

from . import upload_samples as s

PROJECT_APPS = {
    "core", "accounts", "branches", "programs", "events", "registrations", "prayer", "contact", "newsletter",
    "media_library", "resources", "news", "giving", "leadership", "audit", "portal", "membership", "finance",
    "logistics", "missions", "discipleship", "communications", "development",
}  # fmt: skip


def upload(name: str, data: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data)


def rejects(name: str, data: bytes, policy: str, match: str = "") -> None:
    with pytest.raises(ValidationError, match=match or None):
        validate_upload(upload(name, data), policy)


# ------------------------------------------------------------------ every field has a policy
def _all_file_fields() -> list[tuple[str, models.FileField]]:
    out = []
    for model in apps.get_models():
        if model._meta.app_label not in PROJECT_APPS:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, models.FileField):
                out.append((f"{model._meta.label}.{field.name}", field))
    return out


def test_every_file_and_image_field_declares_a_policy() -> None:
    fields = _all_file_fields()
    assert len(fields) >= 30  # the project's upload fields (sanity: the enumeration really ran)
    missing = [
        label
        for label, field in fields
        if not isinstance(field, PolicyFieldMixin)
        or field.upload_policy not in POLICIES
        or PolicyValidator(field.upload_policy) not in field.validators
        or any(isinstance(v, MissingPolicyValidator) for v in field.validators)
    ]
    assert missing == [], f"Upload fields without a policy: {missing}"


def test_private_policies_use_private_storage_and_public_ones_do_not() -> None:
    for label, field in _all_file_fields():
        private = POLICIES[field.upload_policy].private
        assert isinstance(field.storage, PrivateStorage) == private, label


def test_policy_table_matches_the_ministry_rules() -> None:
    mb = upload_policy.MB
    expect = {
        "logo": ({"png", "webp"}, 2),
        "favicon": ({"png"}, 2),
        "hero_photo": ({"jpg", "jpeg", "png", "webp"}, 5),
        "hero_video": ({"mp4", "webm"}, 15),
        "content_image": ({"jpg", "jpeg", "png", "webp"}, 3),
        "gallery_photo": ({"jpg", "jpeg", "png", "webp"}, 8),
        "sermon_audio": ({"mp3", "m4a"}, 50),
        "public_document": ({"pdf"}, 10),
        "finance_receipt": ({"pdf", "jpg", "jpeg", "png"}, 5),
        "office_document": ({"pdf", "docx", "xlsx", "jpg", "jpeg", "png"}, 20),
        "site_photo": ({"jpg", "jpeg", "png", "webp"}, 8),
        "csv_import": ({"csv"}, 2),
    }
    for code, (exts, size) in expect.items():
        assert set(POLICIES[code].extensions) == exts, code
        assert POLICIES[code].max_bytes == size * mb, code
    assert POLICIES["hero_photo"].min_width == 1600 and POLICIES["hero_video"].max_seconds == 15
    for policy in POLICIES.values():  # SVG, HTML, scripts and executables are never in any policy
        assert not set(policy.extensions) & upload_policy.BLOCKED_EXTENSIONS


def test_no_public_form_has_a_file_input(client: Any, db: Any) -> None:
    for url in ("/contact/", "/prayer/", "/get-involved/", "/partner/", "/give/", "/membership/register/",
                "/discipleship/register/", "/finance/volunteer/", "/newsletter/subscribe/"):  # fmt: skip
        resp = client.get(url)
        if resp.status_code == 404:
            continue
        assert resp.status_code == 200, url
        assert b'type="file"' not in resp.content and b"multipart" not in resp.content, url


# ------------------------------------------------------------------ good files pass
@pytest.mark.parametrize(
    ("name", "factory", "policy"),
    [
        ("hero.jpg", lambda: s.jpeg(1800, 900), "hero_photo"),
        ("logo.png", lambda: s.png(alpha=True), "logo"),
        ("logo.webp", s.webp, "logo"),
        ("photo.webp", s.webp, "gallery_photo"),
        ("report.pdf", s.pdf, "public_document"),
        ("budget.docx", s.docx, "office_document"),
        ("loop.mp4", s.mp4, "hero_video"),
        ("loop.webm", s.webm, "hero_video"),
        (
            "targets.csv",
            lambda: "category,name\r\névangélisation,Écoles\r\n".encode(),
            "csv_import",
        ),
        ("sermon.mp3", s.mp3, "sermon_audio"),
        ("receipt.v2.pdf", s.pdf, "finance_receipt"),
    ],
)
def test_valid_files_are_accepted(name: str, factory: Any, policy: str) -> None:
    validate_upload(upload(name, factory()), policy)


# ------------------------------------------------------------------ malicious and wrong files
def test_wrong_extension_for_the_policy() -> None:
    rejects("logo.jpg", s.jpeg(), "logo", "not accepted here")
    rejects("photo.pdf", s.pdf(), "gallery_photo", "not accepted here")


def test_content_must_match_the_extension() -> None:
    rejects("photo.jpg", s.png(), "gallery_photo", "does not match")  # a PNG renamed .jpg
    rejects("report.pdf", s.jpeg(), "public_document", "does not match")


def test_renamed_executable() -> None:
    rejects("photo.jpg", s.EXE, "gallery_photo", "never accepted")
    rejects("invoice.pdf", s.EXE, "finance_receipt", "never accepted")
    rejects("setup.exe", s.EXE, "office_document", "never accepted")


def test_polyglot_image_with_html_payload() -> None:
    rejects("photo.jpg", s.polyglot_jpeg(), "gallery_photo", "embedded web code")


def test_oversized_file(monkeypatch: Any) -> None:
    small = dataclasses.replace(POLICIES["content_image"], max_bytes=1024)
    monkeypatch.setitem(POLICIES, "content_image", small)
    rejects("photo.jpg", s.jpeg(), "content_image", "too large")


def test_pixel_bomb() -> None:
    rejects(
        "bomb.png",
        s.pixel_bomb(10_000),
        "gallery_photo",
        "could not be read|too many pixels",
    )
    rejects(
        "bomb.png",
        s.pixel_bomb(7_000),
        "gallery_photo",
        "could not be read|too many pixels",
    )


def test_image_below_minimum_width() -> None:
    rejects("hero.jpg", s.jpeg(1200, 600), "hero_photo", "at least 1600")


def test_svg_with_script_is_rejected_by_name_and_by_content() -> None:
    rejects("logo.svg", s.SVG_SCRIPT, "logo", "never accepted")
    rejects("logo.png", s.SVG_SCRIPT, "logo", "never accepted|does not match")
    rejects("page.html", s.HTML, "public_document", "never accepted")
    rejects("page.pdf", s.HTML, "public_document", "never accepted|does not match")


def test_macro_office_documents() -> None:
    rejects("budget.docm", s.docx_with_macro(), "office_document", "Macro-enabled")
    rejects("budget.xlsm", s.docx_with_macro(), "office_document", "Macro-enabled")
    rejects("budget.docx", s.docx_with_macro(), "office_document", "macros")
    rejects(
        "budget.docx",
        s.docx({"word/embeddings/oleObject1.bin": b"x"}),
        "office_document",
        "embedded",
    )


def test_zip_bomb_office_document() -> None:
    rejects(
        "budget.docx",
        s.docx_zip_bomb(),
        "office_document",
        "compression bomb|unreasonable size",
    )


def test_pdf_with_javascript_or_launch_actions() -> None:
    rejects("report.pdf", s.pdf_javascript(), "public_document", "scripts, actions")
    rejects(
        "report.pdf",
        s.pdf_obfuscated_javascript(),
        "public_document",
        "scripts, actions",
    )
    rejects(
        "report.pdf",
        s.pdf_launch_in_compressed_stream(),
        "public_document",
        "scripts, actions",
    )
    rejects("report.pdf", s.pdf(b"<< /Encrypt 5 0 R >>"), "public_document", "encrypted")


def test_double_extension_and_hidden_names() -> None:
    rejects("photo.php.jpg", s.jpeg(), "gallery_photo", "two extensions")
    rejects("photo.exe.png", s.png(), "gallery_photo", "two extensions")
    rejects(".htaccess.jpg", s.jpeg(), "gallery_photo", "not allowed")


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/passwd.jpg",
        "..\\..\\boot.jpg",
        "a\x00.jpg",
        "dir/photo.jpg",
        "ph‮otogpj.jpg",
    ],
)
def test_path_traversal_and_control_characters_in_names(name: str) -> None:
    file = File(
        io.BytesIO(s.jpeg()), name=name
    )  # a raw File keeps the name (uploads are pre-cleaned by Django)
    with pytest.raises(ValidationError, match="file name is not allowed"):
        validate_upload(file, "gallery_photo")


def test_video_checks() -> None:
    rejects("loop.mp4", s.mp4(seconds=20), "hero_video", "seconds long")
    rejects("loop.mp4", s.mp4(codec=b"hvc1"), "hero_video", "H.264")
    rejects("loop.mp4", s.mp4(audio=True), "hero_video", "without sound")
    rejects("loop.mp4", s.mp4(size=(3840, 2160)), "hero_video", "1080p")
    rejects("loop.webm", s.webm(seconds=40), "hero_video", "seconds long")
    rejects("loop.webm", s.webm(codec=b"V_THEORA"), "hero_video", "VP8")
    rejects("loop.webm", s.webm(audio=True), "hero_video", "without sound")
    rejects("loop.mp4", s.webm(), "hero_video", "does not match")
    rejects("loop.mov", s.mp4(), "hero_video", "not accepted here")


def test_csv_must_be_utf8_text() -> None:
    rejects("targets.csv", "name\nÉcole\n".encode("utf-16"), "csv_import")
    rejects("targets.xlsx", s.docx(), "csv_import", "not accepted here")


# ------------------------------------------------------------------ the storage hook and the admin limits
@pytest.mark.django_db
def test_storage_hook_validates_files_saved_without_a_form(tmp_path: Any, settings: Any) -> None:
    settings.MEDIA_ROOT = tmp_path
    from branches.models import Branch, Country

    branch = Branch(country=Country.objects.create(name="Testland", code="TL"), name="T", slug="t")
    branch.image = upload("photo.jpg", s.EXE)
    with pytest.raises(ValidationError):
        branch.save()
    assert not list(tmp_path.rglob("*.jpg"))


@pytest.mark.django_db
def test_super_admin_can_tighten_a_limit_without_code() -> None:
    from django.core.cache import cache

    from core.models import UploadLimit

    validate_upload(upload("photo.jpg", s.jpeg(1800, 900)), "content_image")
    UploadLimit.objects.create(policy="content_image", max_mb="0.1")
    cache.clear()
    big = s.jpeg(3000, 3000, "red")
    if len(big) <= 100 * 1024:
        big += b"\x00" * (110 * 1024)
    rejects("photo.jpg", big, "content_image", "too large")
    limit = UploadLimit(policy="content_image", max_mb=Decimal("500"))
    with pytest.raises(ValidationError):
        limit.clean()  # never above the web server cap


@pytest.mark.django_db
def test_upload_limits_admin_is_super_admin_only(
    make_staff: Any, verified_client: Any, admin_prefix: str
) -> None:
    from accounts.roles import FOUNDER, MEDIA

    for user, expected in (
        (make_staff(MEDIA), 403),
        (make_staff(FOUNDER), 403),
        (make_staff(superuser=True), 200),
    ):
        resp = verified_client(user).get(f"{admin_prefix}core/uploadlimit/")
        assert resp.status_code == expected


def test_accept_attribute_is_only_a_hint() -> None:
    from leadership.models import Leader

    field = Leader._meta.get_field("photo").formfield()
    assert field.widget.attrs["accept"] == ".jpg,.jpeg,.png,.webp"


@pytest.mark.django_db
def test_request_body_limits(client: Any, admin_prefix: str) -> None:
    resp = client.post(
        "/contact/",
        data=b"x",
        content_type="text/plain",
        CONTENT_LENGTH=str(2 * 1024 * 1024),
    )
    assert resp.status_code == 413
    resp = client.post(f"{admin_prefix}account/login/", data=b"x", content_type="text/plain",
                       CONTENT_LENGTH=str(61 * 1024 * 1024))  # fmt: skip
    assert resp.status_code == 413


def test_django_body_settings() -> None:
    from django.conf import settings

    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE <= 2 * 1024 * 1024
    assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE <= 2 * 1024 * 1024
    assert max(p.max_bytes for p in POLICIES.values()) <= settings.MAX_STAFF_REQUEST_BYTES


# ------------------------------------------------------------------ ClamAV (optional)
class _FakeClamd(socketserver.BaseRequestHandler):
    reply = b"stream: OK\0"

    def handle(self) -> None:
        assert self.request.recv(10) == b"zINSTREAM\0"
        while True:
            (length,) = struct.unpack(">I", self.request.recv(4))
            if length == 0:
                break
            remaining = length
            while remaining:
                remaining -= len(self.request.recv(remaining))
        self.request.sendall(self.reply)


@pytest.mark.parametrize(
    ("reply", "ok"),
    [(b"stream: OK\0", True), (b"stream: Eicar-Test-Signature FOUND\0", False)],
)
def test_clamav_scan_when_enabled(reply: bytes, ok: bool) -> None:
    handler = type("H", (_FakeClamd,), {"reply": reply})
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        threading.Thread(target=server.handle_request, daemon=True).start()
        with override_settings(
            CLAMAV_ENABLED=True,
            CLAMAV_HOST="127.0.0.1",
            CLAMAV_PORT=server.server_address[1],
        ):
            if ok:
                validate_upload(upload("report.pdf", s.pdf()), "public_document")
            else:
                rejects("report.pdf", s.pdf(), "public_document", "virus scanner")


@override_settings(CLAMAV_ENABLED=True, CLAMAV_HOST="127.0.0.1", CLAMAV_PORT=1, CLAMAV_TIMEOUT=1)
def test_clamav_unreachable_fails_closed() -> None:
    rejects("report.pdf", s.pdf(), "public_document", "not available")
