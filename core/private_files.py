"""Private uploads (receipts, vouchers, permits, contracts, member documents, field photos).

They are stored under ``PRIVATE_MEDIA_ROOT``, which is NOT inside ``MEDIA_ROOT``, so the reverse proxy can
never serve them. The only way to read one is a permission-checked, audit-logged portal view
(``portal.views.resource_file``). Same safety pipeline as public uploads (CLAUDE.md rule 8): extension
whitelist + libmagic content check + size cap + random name; images are decoded and re-encoded, which strips
EXIF/GPS metadata.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage
from django.db import models

from .uploads import (
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
    _ext,
    sanitise_image,
    validate_image_upload,
    validate_pdf_upload,
)


class PrivateStorage(FileSystemStorage):
    """File system storage rooted at PRIVATE_MEDIA_ROOT (read on every use) that has NO public URL."""

    @property
    def base_location(self) -> str:  # type: ignore[override]
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self) -> str:  # type: ignore[override]
        return os.path.abspath(self.base_location)

    def url(self, name: str | None) -> str:
        raise ValueError("Private files have no public URL; use the staff-portal download view.")


def private_storage() -> FileSystemStorage:
    """Callable storage (serialises cleanly in migrations)."""
    return PrivateStorage()


def validate_document_upload(file: File) -> None:
    if getattr(file, "_committed", False) and not hasattr(file, "content_type"):
        return
    ext = _ext(file.name)
    if ext in PDF_EXTENSIONS:
        validate_pdf_upload(file)
    elif ext in IMAGE_EXTENSIONS:
        validate_image_upload(file)
    else:
        raise ValidationError("Only PDF, JPG, PNG or WebP files are allowed.")


class PrivateFileField(models.FileField):
    """PDF or image, stored privately. ``images_only=True`` for photo fields."""

    def __init__(self, *args: Any, images_only: bool = False, **kwargs: Any) -> None:
        self.images_only = images_only
        kwargs.setdefault("max_length", 255)
        kwargs["storage"] = private_storage
        super().__init__(*args, **kwargs)
        validator = validate_image_upload if images_only else validate_document_upload
        if validator not in self.validators:
            self.validators.append(validator)

    def deconstruct(self):  # type: ignore[no-untyped-def]
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("storage", None)
        if self.images_only:
            kwargs["images_only"] = True
        return name, path, args, kwargs

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        file = getattr(model_instance, self.attname)
        if file and not file._committed and _ext(file.name) in IMAGE_EXTENSIONS:
            data, ext, _img = sanitise_image(file)
            file.save(f"upload.{ext}", ContentFile(data), save=False)
            return file
        return super().pre_save(model_instance, add)
