from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra: Any) -> User:
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.update(is_staff=True, is_superuser=True)
        return self._create(email, password, **extra)

    def get_by_natural_key(self, username: str) -> User:
        return self.get(email__iexact=username)


class User(AbstractBaseUser, PermissionsMixin):
    """Staff account. The public never signs in; only ministry staff have accounts."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    is_staff = models.BooleanField(default=False, help_text="Can sign in to the admin (2FA required).")
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="coordinators",
        help_text="Required for Branch Coordinators: limits them to this branch's data.",
    )
    # Account lifecycle (managed ONLY by a Super Admin through accounts.services).
    deactivated_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Soft-deleted: kept for the audit history, cannot sign in.",
    )
    dormant_flagged_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["full_name"]

    class Meta:
        ordering: ClassVar = ["email"]

    def __str__(self) -> str:
        return self.full_name or self.email

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return (self.full_name or self.email).split(" ")[0]

    def in_group(self, *names: str) -> bool:
        return self.groups.filter(name__in=names).exists()

    @property
    def is_super_admin(self) -> bool:
        return bool(self.is_superuser and self.is_active and self.deleted_at is None)

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .guard import check_user_save

        check_user_save(self, kwargs.get("update_fields"))
        super().save(*args, **kwargs)


class Invitation(models.Model):
    """Single-use, expiring link to set a password (new account invite or a forced password reset).

    Only a SHA-256 hash of the token is stored; the token itself exists only in the email that was sent.
    """

    class Kind(models.TextChoices):
        INVITE = "invite", "New account invitation"
        RESET = "reset", "Password reset (forced by a Super Admin)"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invitations")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.INVITE)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} #{self.pk}"

    @property
    def audit_label(self) -> str:
        return f"invitation #{self.pk}"

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.revoked_at is None and self.expires_at > timezone.now()

    @property
    def state(self) -> str:
        if self.used_at:
            return "used"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "open"


class AccountIntegrityState(models.Model):
    """One row: HMAC fingerprint of every account's privileged state, as last approved (accounts.integrity)."""

    fingerprint = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "account integrity state"

    def __str__(self) -> str:
        return "Account integrity state"
