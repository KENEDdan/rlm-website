"""Safe upload pipeline (CLAUDE.md rule 8).

* Extension whitelist AND content sniffing with libmagic
* Size caps from settings.UPLOAD_LIMITS
* Random file names (uuid4), date-based folders
* Images are fully decoded and re-encoded with Pillow: EXIF/GPS and any trailing payload are dropped
* WebP renditions (480/960/1600 px wide) generated for responsive ``srcset``
"""

from __future__ import annotations

import io
import os
import uuid
import warnings
from collections.abc import Callable
from typing import Any

import magic
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.db import models
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard (~40 MP)

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
PDF_EXTENSIONS = {"pdf"}
PDF_MIME = {"application/pdf"}
AUDIO_EXTENSIONS = {"mp3", "m4a"}
AUDIO_MIME = {"audio/mpeg", "audio/mp4", "audio/x-m4a", "video/mp4", "audio/mp3"}

RENDITION_WIDTHS = (480, 960, 1600)
MASTER_MAX_WIDTH = 2400


def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def _sniff(file: File) -> str:
    pos = file.tell() if hasattr(file, "tell") else 0
    file.seek(0)
    head = file.read(4096)
    file.seek(pos)
    return magic.from_buffer(head, mime=True)


def _check_size(file: File, kind: str) -> None:
    limit = settings.UPLOAD_LIMITS[kind]
    if file.size and file.size > limit:
        raise ValidationError(f"File too large. Maximum size is {limit // (1024 * 1024)} MB.")


def validate_image_upload(file: File) -> None:
    if getattr(file, "_committed", False) and not hasattr(file, "content_type"):
        return  # already stored and sanitised
    if _ext(file.name) not in IMAGE_EXTENSIONS:
        raise ValidationError("Only JPG, PNG or WebP images are allowed.")
    _check_size(file, "image")
    if _sniff(file) not in IMAGE_MIME:
        raise ValidationError("The file content is not a valid image.")
    try:
        file.seek(0)
        # Pillow only WARNS between 1x and 2x MAX_IMAGE_PIXELS; treat that range as an error too.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as img:
                img.verify()
        file.seek(0)
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError("The image could not be read.") from exc


def validate_pdf_upload(file: File) -> None:
    if getattr(file, "_committed", False) and not hasattr(file, "content_type"):
        return
    if _ext(file.name) not in PDF_EXTENSIONS:
        raise ValidationError("Only PDF files are allowed.")
    _check_size(file, "pdf")
    if _sniff(file) not in PDF_MIME:
        raise ValidationError("The file content is not a valid PDF.")
    file.seek(0)
    if file.read(5) != b"%PDF-":
        raise ValidationError("The file content is not a valid PDF.")
    file.seek(0)


def validate_audio_upload(file: File) -> None:
    if getattr(file, "_committed", False) and not hasattr(file, "content_type"):
        return
    if _ext(file.name) not in AUDIO_EXTENSIONS:
        raise ValidationError("Only MP3 or M4A audio is allowed.")
    _check_size(file, "audio")
    if _sniff(file) not in AUDIO_MIME:
        raise ValidationError("The file content is not valid audio.")


def random_upload_to(prefix: str) -> Callable[[Any, str], str]:
    """Return an ``upload_to`` callable producing ``<prefix>/YYYY/MM/<uuid>.<ext>``."""

    def _upload_to(instance: Any, filename: str) -> str:
        ext = _ext(filename) or "bin"
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


def sanitise_image(file: File) -> tuple[bytes, str, Image.Image]:
    """Decode and re-encode an image. Returns (bytes, extension, pillow image)."""
    file.seek(0)
    with Image.open(file) as src:
        img = ImageOps.exif_transpose(src)
        img.load()
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")
    if img.width > MASTER_MAX_WIDTH:
        img = ImageOps.contain(img, (MASTER_MAX_WIDTH, MASTER_MAX_WIDTH * 4))
    out = io.BytesIO()
    if has_alpha:
        img.save(out, format="PNG", optimize=True)  # fresh image object: no EXIF/ICC/text chunks
        ext = "png"
    else:
        img.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
        ext = "jpg"
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


class SafeImageField(models.ImageField):
    """ImageField that validates, sanitises and creates WebP renditions on save."""

    default_validators = [validate_image_upload]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_length", 255)
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        file = getattr(model_instance, self.attname)
        if file and not file._committed:
            data, ext, img = sanitise_image(file)
            file.save(f"upload.{ext}", ContentFile(data), save=False)
            for width, blob in build_renditions(img).items():
                file.storage.save(rendition_name(file.name, width), ContentFile(blob))
        return file


class SafeFileField(models.FileField):
    """FileField with random names; pass ``kind`` = 'pdf' or 'audio' for validation."""

    def __init__(self, *args: Any, kind: str = "pdf", **kwargs: Any) -> None:
        self.kind = kind
        kwargs.setdefault("max_length", 255)
        super().__init__(*args, **kwargs)
        validator = {"pdf": validate_pdf_upload, "audio": validate_audio_upload}[kind]
        if validator not in self.validators:
            self.validators.append(validator)

    def deconstruct(self):  # type: ignore[no-untyped-def]
        name, path, args, kwargs = super().deconstruct()
        kwargs["kind"] = self.kind
        return name, path, args, kwargs
