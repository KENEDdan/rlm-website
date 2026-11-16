"""Encrypted model fields.

Values are encrypted in ``get_prep_value`` and decrypted in ``from_db_value``; the database only ever sees
Fernet tokens. Encrypted columns cannot be filtered (ciphertext is non-deterministic). Use a blind index
field (see ``core.crypto.blind_index``) for exact-match lookups such as email.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.core import validators
from django.db import models

from .crypto import DECRYPTION_FAILED, decrypt_str, encrypt_str


class EncryptedTextField(models.TextField):
    description = "Text encrypted at rest with Fernet"

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        if value == DECRYPTION_FAILED:
            # A row read while a key was missing must never be written back: that would replace the
            # real (still recoverable) ciphertext with the placeholder text.
            raise ValueError("Refusing to save a value that could not be decrypted.")
        return encrypt_str(str(value))

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is None or value == "":
            return value
        return decrypt_str(value)

    def get_lookup(self, lookup_name: str):  # type: ignore[override]
        if lookup_name not in {"isnull", "exact"}:
            raise NotImplementedError(f"Encrypted fields do not support the '{lookup_name}' lookup.")
        if lookup_name == "exact":
            # Exact only works for the empty string (blank values are stored unencrypted).
            return EmptyOnlyExact
        return super().get_lookup(lookup_name)


class EmptyOnlyExact(models.lookups.Exact):
    def get_prep_lookup(self) -> Any:
        if self.rhs not in ("", None):
            raise NotImplementedError("Encrypted fields can only be compared with ''. Use a blind index.")
        return self.rhs


class EncryptedCharField(EncryptedTextField):
    """Short encrypted text; ``max_length`` limits the plaintext, the column is TEXT."""

    def __init__(self, *args: Any, max_length: int = 255, **kwargs: Any) -> None:
        self.plain_max_length = max_length
        super().__init__(*args, **kwargs)
        self.validators.append(validators.MaxLengthValidator(max_length))

    def deconstruct(self):  # type: ignore[no-untyped-def]
        name, path, args, kwargs = super().deconstruct()
        kwargs["max_length"] = self.plain_max_length
        return name, path, args, kwargs

    def formfield(self, **kwargs: Any) -> forms.Field:
        defaults: dict[str, Any] = {"form_class": forms.CharField, "max_length": self.plain_max_length}
        defaults.update(kwargs)
        # Skip TextField.formfield (it forces a Textarea); short values use a text input.
        return models.Field.formfield(self, **defaults)


class EncryptedEmailField(EncryptedCharField):
    default_validators = [validators.validate_email]

    def __init__(self, *args: Any, max_length: int = 254, **kwargs: Any) -> None:
        super().__init__(*args, max_length=max_length, **kwargs)

    def formfield(self, **kwargs: Any) -> forms.Field:
        defaults: dict[str, Any] = {"form_class": forms.EmailField, "max_length": self.plain_max_length}
        defaults.update(kwargs)
        return models.Field.formfield(self, **defaults)


def encrypted_fields(model: type[models.Model]) -> list[str]:
    return [f.name for f in model._meta.concrete_fields if isinstance(f, EncryptedTextField)]
