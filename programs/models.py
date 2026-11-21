"""Ministry activities: four categories, each with its activities (replaced the five programmes, D-035).

Everything here is data managed by the Technical Team in the admin: a new activity or category needs no code.
``Activity.department`` routes the activity to a staff dashboard (and its events and indicators); only the
Super Admin may change it.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.db.models import Q
from django.urls import reverse

from core.models import PublishableModel, PublishedQuerySet
from core.uploads import RandomUploadTo, SafeImageField
from core.validators import SAFE_LINK_HELP, is_safe_link, validate_safe_link


class Icon(models.TextChoices):
    FLAME = "flame", "Flame"
    BOOK = "book", "Open book"
    PEOPLE = "people", "People"
    GLOBE = "globe", "Globe"
    HANDS = "hands", "Praying hands"
    STAR = "star", "Star"
    HEART = "heart", "Heart"


class ActivityCategory(PublishableModel):
    title = models.CharField(max_length=140, unique=True)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True, help_text="Plain text. Blank lines separate paragraphs.")
    icon = models.CharField(max_length=20, choices=Icon.choices, default=Icon.FLAME)
    image = SafeImageField(upload_to=RandomUploadTo("activities"), policy="content_image", blank=True)
    image_alt = models.CharField(max_length=200, blank=True)
    department = models.ForeignKey(
        "portal.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_categories",
        help_text="Default staff department for NEW activities in this category (Super Admin only).",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["order", "title"]
        verbose_name = "activity category"
        verbose_name_plural = "activity categories"

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("programs:category", args=[self.slug])


class ActivityQuerySet(PublishedQuerySet):
    def published(self) -> ActivityQuerySet:  # type: ignore[override]
        """Published activities in a published category."""
        return self.filter(is_published=True, category__is_published=True)

    def for_branch(self, branch: Any) -> ActivityQuerySet:
        """Offered in this branch: activities with no branches listed run in every branch."""
        return self.filter(Q(branches__isnull=True) | Q(branches=branch)).distinct()


class Activity(PublishableModel):
    category = models.ForeignKey(ActivityCategory, on_delete=models.PROTECT, related_name="activities")
    title = models.CharField(max_length=140)
    summary = models.CharField(max_length=300)
    body = models.TextField(blank=True, help_text="Plain text. Blank lines separate paragraphs.")
    icon = models.CharField(max_length=20, choices=Icon.choices, default=Icon.FLAME)
    image = SafeImageField(upload_to=RandomUploadTo("activities"), policy="content_image", blank=True)
    image_alt = models.CharField(max_length=200, blank=True)
    schedule = models.CharField(
        "schedule / frequency",
        max_length=160,
        blank=True,
        help_text="e.g. 'Every last Friday of the month, 6 pm' or 'Once a year, in August'.",
    )
    branches = models.ManyToManyField(
        "branches.Branch",
        blank=True,
        related_name="ministry_activities",
        help_text="Where it runs. Leave empty for all branches.",
    )
    department = models.ForeignKey(
        "portal.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        help_text="Staff department whose dashboard this activity feeds (Super Admin only).",
    )
    cta_label = models.CharField(
        "'Get involved' button", max_length=40, default="Get involved", help_text="Words on the button."
    )
    cta_link = models.CharField(
        "'Get involved' link",
        max_length=300,
        blank=True,
        validators=[validate_safe_link],
        help_text=SAFE_LINK_HELP + " Leave empty for the volunteer form.",
    )
    is_featured = models.BooleanField(default=True, help_text="Show on the home page.")
    order = models.PositiveSmallIntegerField(default=0)

    objects = ActivityQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["category__order", "order", "title"]
        verbose_name_plural = "activities"

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.department_id is None and self.category_id and not self.pk:
            self.department_id = self.category.department_id  # default routing for a new activity
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("programs:detail", args=[self.slug])

    @property
    def safe_cta_link(self) -> str:
        if self.cta_link and is_safe_link(self.cta_link):
            return self.cta_link
        return reverse("registrations:volunteer")
