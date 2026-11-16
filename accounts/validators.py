from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


class ComplexityValidator:
    """Require at least three of: lowercase, uppercase, digit, symbol."""

    def validate(self, password: str, user: Any = None) -> None:
        classes = [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
        if sum(classes) < 3:
            raise ValidationError(
                "Use at least three of: lowercase letters, uppercase letters, numbers, symbols.",
                code="password_too_simple",
            )

    def get_help_text(self) -> str:
        return "Your password must mix at least three of: lowercase, uppercase, numbers and symbols."
