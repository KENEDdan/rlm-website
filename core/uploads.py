"""Upload field classes (CLAUDE.md rule 8). The checks themselves live in ``core.upload_policy``.

* Every field names a policy (``policy="content_image"``) - the policy decides formats, size and limits
* Validation runs in every ModelForm (field validator) AND again in ``pre_save`` (storage hook), so a file
  assigned in code without a form is still checked before it is stored
* Random file names (uuid4), date-based folders; the visitor's file name is never used
* Images are fully decoded and re-encoded with Pillow: EXIF/GPS and any trailing payload are dropped
* WebP renditions (480/960/1600 px wide) generated for responsive ``srcset`` (public images)
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import Callable
from typing import Any

from django import forms
from django.core.files.base import ContentFile, File
from django.db import models
from django.utils import timezone
from PIL import Image, ImageOps

from .upload_policy import POLICIES, MissingPolicyValidator, PolicyValidator, get_policy, validate_upload

RENDITION_WIDTHS = (480, 960, 1600)
MASTER_MAX_WIDTH = 2400
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def random_upload_to(prefix: str) -> Callable[[Any, str], str]:
    """Return an ``upload_to`` callable producing ``<prefix>/YYYY/MM/<uuid>.<ext>``."""

    def _upload_to(instance: Any, filename: str) -> str:
        ext = _ext(filename)
        if not ext.isalnum() or len(ext) > 5:
            ext = "bin"
        now = timezone.now()
        return f"{prefix}/{now:%Y/%m}/{uuid.uuid4().hex}.{ext}"

    _upload_to.__qualname__ = f"random_upload_to.{prefix}"
    return _upload_to


class RandomUploadTo:
    """Serialisable (migration-safe) ``upload_to`` that randomises file names."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def __call__(self, instance: Any, filename: str) -> str:
        return random_upload_to(self.prefix)(instance, filename)

    def deconstruct(self):  # type: ignore[no-untyped-def]
        return ("core.uploads.RandomUploadTo", (self.prefix,), {})

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RandomUploadTo) and other.prefix == self.prefix


def sanitise_image(file: File, output: str = "") -> tuple[bytes, str, Image.Image]:
    """Decode and re-encode an image. Returns (bytes, extension, pillow image).

    ``output="png"`` always writes PNG (logos, favicons); otherwise PNG when the image has transparency,
    JPEG when it does not. A fresh image object carries no EXIF, GPS, ICC or text chunks.
    """
    file.seek(0)
    with Image.open(file) as src:
        img = ImageOps.exif_transpose(src)
        img.load()
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")
    if img.width > MASTER_MAX_WIDTH:
        img = ImageOps.contain(img, (MASTER_MAX_WIDTH, MASTER_MAX_WIDTH * 4))
    out = io.BytesIO()
    if has_alpha or output == "png":
        img.save(out, format="PNG", optimize=True)
        ext = "png"
    else:
        img.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
        ext = "jpg"
    file.seek(0)
    return out.getvalue(), ext, img


def rendition_name(name: str, width: int) -> str:
    stem, _ = os.path.splitext(name)
    return f"{stem}_w{width}.webp"


def build_renditions(img: Image.Image) -> dict[int, bytes]:
    result: dict[int, bytes] = {}
    for width in RENDITION_WIDTHS:
        target = img if img.width <= width else ImageOps.contain(img, (width, width * 4))
        buf = io.BytesIO()
        target.save(buf, format="WEBP", quality=78, method=4)
        result[width] = buf.getvalue()
    return result


class PolicyFieldMixin:
    """Shared by every upload field: a policy, its validator, help text, ``accept`` hint and the storage hook."""

    upload_policy: str

    def _init_policy(self, policy: str | None, kwargs: dict[str, Any]) -> None:
        # Old migrations still pass these; the policy replaced them.
        kwargs.pop("kind", None)
        kwargs.pop("images_only", None)
        if policy is not None and policy not in POLICIES:
            raise TypeError(f"Unknown upload policy {policy!r} (one of {sorted(POLICIES)}).")
        # No policy (only historical migration states): every upload is refused (fail closed), and
        # tests/test_upload_policies.py fails for any real model field without one.
        self.upload_policy = policy or ""
        kwargs.setdefault("max_length", 255)
        if policy:
            kwargs.setdefault("help_text", POLICIES[policy].help_text)

    def _add_validator(self) -> None:
        validator = PolicyValidator(self.upload_policy) if self.upload_policy else MissingPolicyValidator()
        if validator not in self.validators:  # type: ignore[attr-defined]
            self.validators.append(validator)  # type: ignore[attr-defined]

    def formfield(self, **kwargs: Any) -> Any:
        field = super().formfield(**kwargs)  # type: ignore[misc]
        if (
            field is not None
            and self.upload_policy
            and isinstance(field.widget, forms.ClearableFileInput | forms.FileInput)
        ):
            field.widget.attrs["accept"] = get_policy(self.upload_policy).accept  # UX hint only
        return field

    def check_new_file(self, model_instance: models.Model) -> Any:
        """Storage hook: validate an uncommitted file before it is written, unless its form already did."""
        file = getattr(model_instance, self.attname)  # type: ignore[attr-defined]
        if file and not file._committed and getattr(file, "_rlm_validated", None) != self.upload_policy:
            if not self.upload_policy:
                MissingPolicyValidator()(file)
            validate_upload(file, self.upload_policy)
            file._rlm_validated = self.upload_policy
        return file

    def deconstruct(self):  # type: ignore[no-untyped-def]
        name, path, args, kwargs = super().deconstruct()  # type: ignore[misc]
        if not self.upload_policy:
            return name, path, args, kwargs
        kwargs["policy"] = self.upload_policy
        if kwargs.get("help_text") == POLICIES[self.upload_policy].help_text:
            del kwargs["help_text"]  # derived from the policy, so limit changes need no migration
        return name, path, args, kwargs


class SafeImageField(PolicyFieldMixin, models.ImageField):
    """Public image: validated against its policy, re-encoded, with WebP renditions."""

    def __init__(self, *args: Any, policy: str | None = None, **kwargs: Any) -> None:
        self._init_policy(policy, kwargs)
        super().__init__(*args, **kwargs)
        self._add_validator()

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        file = self.check_new_file(model_instance)
        if file and not file._committed:
            data, ext, img = sanitise_image(file, get_policy(self.upload_policy).output)
            file.save(f"upload.{ext}", ContentFile(data), save=False)
            for width, blob in build_renditions(img).items():
                file.storage.save(rendition_name(file.name, width), ContentFile(blob))
        return file


class SafeFileField(PolicyFieldMixin, models.FileField):
    """Public non-image file (PDF, audio, background video) checked against its policy."""

    def __init__(self, *args: Any, policy: str | None = None, **kwargs: Any) -> None:
        self._init_policy(policy, kwargs)
        super().__init__(*args, **kwargs)
        self._add_validator()

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        self.check_new_file(model_instance)
        return super().pre_save(model_instance, add)
