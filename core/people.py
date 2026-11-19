"""Shared bits for records about people: choices, age bands and the minors rule."""

from __future__ import annotations

from datetime import date

from django.db import models
from django.utils import timezone

ADULT_AGE = 18


class Gender(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"


class YesNo(models.TextChoices):
    YES = "yes", "Yes"
    NO = "no", "No"


class AgeBand(models.TextChoices):
    UNDER_18 = "under_18", "Under 18"
    AGE_18_25 = "18_25", "18-25"
    AGE_26_35 = "26_35", "26-35"
    AGE_36_50 = "36_50", "36-50"
    AGE_51_PLUS = "51_plus", "51 and over"
    UNKNOWN = "unknown", "Not known"


def age_on(born: date | None, today: date | None = None) -> int | None:
    if born is None:
        return None
    today = today or timezone.localdate()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def band_for_age(age: int | None) -> str:
    if age is None:
        return AgeBand.UNKNOWN
    if age < ADULT_AGE:
        return AgeBand.UNDER_18
    if age <= 25:
        return AgeBand.AGE_18_25
    if age <= 35:
        return AgeBand.AGE_26_35
    if age <= 50:
        return AgeBand.AGE_36_50
    return AgeBand.AGE_51_PLUS


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
