from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel
from core.uploads import RandomUploadTo, SafeImageField


class PostQuerySet(models.QuerySet):
    def published(self) -> PostQuerySet:
        """Published, plus scheduled posts whose time has come (no background job needed)."""
        return self.filter(
            status__in=[Post.Status.PUBLISHED, Post.Status.SCHEDULED], publish_at__lte=timezone.now()
        )


class Post(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"

    class Kind(models.TextChoices):
        NEWS = "news", "News"
        ANNOUNCEMENT = "announcement", "Announcement"
        REPORT = "report", "Report"
        TESTIMONY = "testimony", "Testimony"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=160, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.NEWS)
    summary = models.CharField(max_length=300)
    body = models.TextField(help_text="Plain text. Blank lines separate paragraphs.")
    image = SafeImageField(upload_to=RandomUploadTo("news"), blank=True)
    image_alt = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="posts"
    )
    department = models.ForeignKey(
        "leadership.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="posts"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    publish_at = models.DateTimeField(
        default=timezone.now, db_index=True, help_text="For scheduled posts: when it should appear."
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-publish_at"]
        verbose_name = "news post"

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        if self.status == self.Status.SCHEDULED and self.publish_at and self.publish_at <= timezone.now():
            raise ValidationError({"publish_at": "A scheduled post needs a publish time in the future."})

    def get_absolute_url(self) -> str:
        return reverse("news:detail", args=[self.slug])

    @property
    def is_live(self) -> bool:
        return self.status != self.Status.DRAFT and self.publish_at <= timezone.now()
