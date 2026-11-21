"""Private uploads (receipts, vouchers, permits, contracts, member documents, field photos).

They are stored under ``PRIVATE_MEDIA_ROOT``, which is NOT inside ``MEDIA_ROOT``, so the reverse proxy can
never serve them. The only way to read one is a permission-checked, audit-logged portal view
(``portal.views.resource_file``) that always sends it as an attachment with a generated file name. The same
policy checks as public uploads apply (``core.upload_policy``); images are decoded and re-encoded, which strips
EXIF/GPS metadata.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import models

from .upload_policy import POLICIES, get_policy
from .uploads import IMAGE_EXTENSIONS, PolicyFieldMixin, _ext, sanitise_image


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


class PrivateFileField(PolicyFieldMixin, models.FileField):
    """A private file checked against a private policy (``finance_receipt``, ``office_document``, ...)."""

    def __init__(self, *args: Any, policy: str | None = None, **kwargs: Any) -> None:
        self._init_policy(policy, kwargs)
        if self.upload_policy and not POLICIES[self.upload_policy].private:
            raise TypeError(f"Policy {policy!r} is for public files; private fields need a private policy.")
        kwargs["storage"] = private_storage
        super().__init__(*args, **kwargs)
        self._add_validator()

    def deconstruct(self):  # type: ignore[no-untyped-def]
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop("storage", None)
        return name, path, args, kwargs

    def pre_save(self, model_instance: models.Model, add: bool) -> Any:
        file = self.check_new_file(model_instance)
        if file and not file._committed and _ext(file.name) in IMAGE_EXTENSIONS:
            data, ext, _img = sanitise_image(file, get_policy(self.upload_policy).output)
            file.save(f"upload.{ext}", ContentFile(data), save=False)
            return file
        return super().pre_save(model_instance, add)
