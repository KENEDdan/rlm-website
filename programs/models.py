from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.urls import reverse

from core.models import PublishableModel
from core.uploads import RandomUploadTo, SafeImageField


class Program(PublishableModel):
    class Icon(models.TextChoices):
        FLAME = "flame", "Flame"
        BOOK = "book", "Open book"
        PEOPLE = "people", "People"
        GLOBE = "globe", "Globe"
        HANDS = "hands", "Praying hands"
        STAR = "star", "Star"
        HEART = "heart", "Heart"

    title = models.CharField(max_length=140)
    summary = models.CharField(max_length=300)
    body = models.TextField(blank=True, help_text="Plain text. Blank lines separate paragraphs.")
    icon = models.CharField(max_length=20, choices=Icon.choices, default=Icon.FLAME)
    image = SafeImageField(upload_to=RandomUploadTo("programs"), policy="content_image", blank=True)
    image_alt = models.CharField(max_length=200, blank=True)
    department = models.ForeignKey(
        "leadership.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="programs"
    )
    is_featured = models.BooleanField(default=True, help_text="Show on the home page.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["order", "title"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("programs:detail", args=[self.slug])
