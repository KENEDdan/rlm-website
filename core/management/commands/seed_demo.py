"""Load clearly FAKE demo content for local development: ``manage.py seed_demo [--reset]``.

* Refuses to run unless DEBUG is on (never on a production server).
* Every item is labelled "DEMO", uses a ``demo-`` slug, and every address is ``@example.test``.
* Idempotent: running it twice does not duplicate anything. ``--reset`` removes only demo items.
* Images are generated (flame-coloured placeholders marked "DEMO"); they are not real ministry photos.
"""

from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from branches.models import Branch
from contact.models import ContactMessage
from core.models import HeroSlide, Partner
from events.models import Event
from giving.models import CurrentNeed, Donation, GivingCategory, PartnershipEnquiry
from media_library.models import Album, Photo, Testimony, Video
from news.models import Post
from newsletter.models import Subscriber
from prayer.models import PrayerRequest
from programs.models import Program
from registrations.models import EventRegistration, VolunteerApplication
from resources.models import Resource, ResourceCategory, Series

DEMO = "demo-"
DEMO_EMAIL_DOMAIN = "@example.test"
DEMO_EMAILS = [f"demo.person{i}{DEMO_EMAIL_DOMAIN}" for i in range(1, 4)] + [
    f"demo.contact{DEMO_EMAIL_DOMAIN}"
]
# Brand palette (CLAUDE.md) for generated placeholder images only.
GRADIENT = [(0xF8, 0xC1, 0x24), (0xF0, 0x65, 0x2A), (0xEE, 0x36, 0x2C)]


def demo_image(label: str, size: tuple[int, int] = (1200, 800)) -> SimpleUploadedFile:
    """A flame-gradient JPEG with 'DEMO' text, run through the normal upload pipeline on save."""
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for x in range(w):
        t = x / max(w - 1, 1)
        a, b, f = (
            (GRADIENT[0], GRADIENT[1], t / 0.55)
            if t < 0.55
            else (GRADIENT[1], GRADIENT[2], (t - 0.55) / 0.45)
        )
        draw.line([(x, 0), (x, h)], fill=tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3)))
    draw.rectangle([0, h - 90, w, h], fill=(0x0A, 0x0A, 0x0A))
    draw.text((24, h - 70), f"DEMO PLACEHOLDER - {label}"[:60], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return SimpleUploadedFile(f"{label}.jpg", buf.getvalue(), content_type="image/jpeg")


class Command(BaseCommand):
    help = "Load fake demo content for local development (refuses to run when DEBUG=False)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--reset", action="store_true", help="Delete demo content instead of creating it."
        )
        parser.add_argument("--no-images", action="store_true", help="Skip generated images (faster).")

    def handle(self, *args: Any, reset: bool = False, no_images: bool = False, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo only runs with DEBUG=True (local development). Nothing was changed."
            )
        with transaction.atomic():
            if reset:
                self.stdout.write(self.style.WARNING(f"Removed {self.reset()} demo item(s)."))
                return
            created = self.seed(images=not no_images)
        self.stdout.write(self.style.SUCCESS(f"Demo content ready ({created} new item(s))."))

    # ------------------------------------------------------------------ reset
    def reset(self) -> int:
        from core.crypto import blind_index

        total = 0
        for model in (Post, Resource, Series, ResourceCategory, Video, Testimony, Album, Event):
            total += model.objects.filter(slug__startswith=DEMO).delete()[0]  # photos cascade with albums
        total += CurrentNeed.objects.filter(title__startswith="DEMO").delete()[0]
        total += HeroSlide.objects.filter(title__startswith="DEMO").delete()[0]
        total += Partner.objects.filter(name__startswith="DEMO").delete()[0]
        # Encrypted columns can't be searched; demo rows are found through the blind index of their address.
        hashes = [blind_index(email) for email in DEMO_EMAILS]
        for model in (PrayerRequest, ContactMessage, VolunteerApplication, PartnershipEnquiry, Subscriber):
            total += model.objects.filter(email_hash__in=hashes).delete()[0]
        total += Donation.objects.filter(donor_email_hash__in=hashes).delete()[0]
        return total

    # ------------------------------------------------------------------ seed
    def seed(self, *, images: bool) -> int:
        self.created = 0
        now = timezone.now()
        juba = Branch.objects.filter(slug="juba").first()
        yei = Branch.objects.filter(slug="yei").first()
        program = Program.objects.order_by("order").first()

        def get_or_create(model: Any, slug: str, image_field: str | None = None, **fields: Any) -> Any:
            obj, new = model.objects.get_or_create(slug=DEMO + slug, defaults=fields)
            if new:
                self.created += 1
                if images and image_field:
                    setattr(obj, image_field, demo_image(slug))
                    obj.save()
            return obj

        # Events: two upcoming (one with registration), one past.
        conf = get_or_create(
            Event,
            "youth-revival-conference",
            "poster",
            title="DEMO Youth Revival Conference",
            summary="Three days of worship, teaching and prayer (demo).",
            description="This is demo content for local development.\n\nReplace it in the admin.",
            program=program,
            branch=juba,
            start=now + timedelta(days=21),
            end=now + timedelta(days=23),
            venue="Demo Hall, Juba",
            registration_open=True,
            capacity=150,
            is_published=True,
        )
        get_or_create(
            Event,
            "yei-prayer-night",
            title="DEMO Prayer Night",
            summary="An evening of prayer (demo).",
            branch=yei,
            start=now + timedelta(days=9),
            end=now + timedelta(days=9, hours=3),
            venue="Demo Church, Yei",
            is_published=True,
        )
        get_or_create(
            Event,
            "past-outreach",
            "poster",
            title="DEMO Community Outreach",
            summary="Past demo event.",
            branch=juba,
            start=now - timedelta(days=40),
            end=now - timedelta(days=40, hours=-5),
            is_published=True,
        )

        # News
        for i, (kind, title) in enumerate(
            [
                (Post.Kind.NEWS, "DEMO Youth conference registration is open"),
                (Post.Kind.REPORT, "DEMO Outreach report"),
                (Post.Kind.ANNOUNCEMENT, "DEMO New branch meeting times"),
            ]
        ):
            get_or_create(
                Post,
                f"news-{i}",
                "image" if i < 2 else None,
                title=title,
                kind=kind,
                summary="Demo news item for local development.",
                body="Demo paragraph one.\n\nDemo paragraph two.",
                status=Post.Status.PUBLISHED,
                publish_at=now - timedelta(days=i * 5),
                branch=juba,
            )

        # Sermons & resources
        cat, _ = ResourceCategory.objects.get_or_create(
            slug=DEMO + "teaching", defaults={"name": "DEMO Teaching"}
        )
        series, _ = Series.objects.get_or_create(
            slug=DEMO + "rebuilding", defaults={"title": "DEMO Rebuilding series"}
        )
        for i, kind in enumerate(
            [Resource.Kind.SERMON, Resource.Kind.SERMON, Resource.Kind.DEVOTIONAL, Resource.Kind.STUDY]
        ):
            get_or_create(
                Resource,
                f"resource-{i}",
                title=f"DEMO {kind.label} {i + 1}",
                kind=kind,
                speaker="Demo Speaker",
                scripture="Acts 15:16",
                summary="Demo resource.",
                body="Demo notes.",
                category=cat,
                series=series if kind == Resource.Kind.SERMON else None,
                date=(now - timedelta(days=7 * i)).date(),
                is_published=True,
            )

        # Gallery
        album = get_or_create(
            Album,
            "conference-album",
            "cover",
            title="DEMO Conference album",
            description="Generated placeholder images.",
            branch=juba,
            event=conf,
            is_published=True,
            cover_alt="Demo placeholder image",
        )
        if images and not album.photos.exists():
            for i in range(4):
                Photo.objects.create(
                    album=album, image=demo_image(f"photo-{i}"), alt_text=f"Demo placeholder {i + 1}"
                )
                self.created += 1
        get_or_create(
            Video,
            "welcome-video",
            title="DEMO Welcome video",
            youtube_url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            description="Public sample video (Big Buck Bunny) as a placeholder.",
            album=album,
            is_published=True,
        )
        get_or_create(
            Testimony,
            "testimony",
            title="DEMO Testimony",
            body="A demo testimony for layout testing.",
            person_display_name="Demo Person",
            name_display=Testimony.NameDisplay.FIRST_NAME,
            consent_confirmed=True,
            subject_is_adult=True,
            is_approved=True,
            is_published=True,
            branch=yei,
        )
        get_or_create(
            Testimony,
            "testimony-2",
            title="DEMO Restored family",
            body="A second demo testimony, shown with initials only.",
            person_display_name="Demo Second Person",
            consent_confirmed=True,
            subject_is_adult=True,
            is_approved=True,
            is_published=True,
            branch=juba,
        )

        # Home hero slides (after the seeded tagline slide) and partner logos
        for i, (title, button, link) in enumerate(
            [
                ("DEMO Serve with us", "Volunteer", "/get-involved/"),
                ("DEMO Youth Revival Conference", "Register", "/events/"),
                ("DEMO Watch the latest sermon", "Watch", "/resources/"),
            ],
            start=1,
        ):
            if not HeroSlide.objects.filter(title=title).exists():
                slide = HeroSlide(
                    title=title,
                    subtitle="Demo slide for local development. Replace it in the admin.",
                    image_alt="Demo placeholder image",
                    button_text=button,
                    button_link=link,
                    order=i * 10,
                )
                if images:
                    slide.image = demo_image(f"hero-{i}", (1920, 900))
                slide.save()
                self.created += 1
        if images:
            for i in range(1, 7):
                if not Partner.objects.filter(name=f"DEMO Partner {i}").exists():
                    Partner.objects.create(
                        name=f"DEMO Partner {i}",
                        logo=demo_image(f"partner-{i}", (400, 160)),
                        website="https://example.org/",
                        order=i,
                        is_published=True,
                    )
                    self.created += 1

        # Giving: a demo need (categories are seeded by migration)
        if not CurrentNeed.objects.filter(title__startswith="DEMO").exists():
            CurrentNeed.objects.create(
                title="DEMO Sound equipment",
                description="Demo need.",
                category=GivingCategory.objects.first(),
                target_amount=Decimal("2000"),
                raised_amount=Decimal("650"),
                is_published=True,
            )
            self.created += 1

        self.seed_submissions(conf, juba)
        return self.created

    def seed_submissions(self, event: Event, branch: Branch | None) -> None:
        """Fake inbox items so staff screens can be tried. Names are obviously fake."""
        from core.crypto import blind_index

        def missing(model: Any, email: str, field: str = "email_hash") -> bool:
            return not model.objects.filter(**{field: blind_index(email)}).exists()

        for i, email in enumerate(DEMO_EMAILS[:3], start=1):
            if missing(PrayerRequest, email):
                PrayerRequest.objects.create(
                    name=f"Demo Person {i}", email=email, request_text="Demo prayer request.", consent=True
                )
                self.created += 1
            if missing(VolunteerApplication, email):
                VolunteerApplication.objects.create(
                    full_name=f"Demo Volunteer {i}",
                    email=email,
                    phone="+000 000 000",
                    country="Demo Country",
                    location="Demo Town",
                    branch=branch,
                    availability="weekends",
                    consent=True,
                )
                self.created += 1
            if missing(EventRegistration, email) and event.pk:
                EventRegistration.objects.create(
                    event=event, full_name=f"Demo Guest {i}", email=email, attendees=1, consent=True
                )
                self.created += 1
        email = DEMO_EMAILS[3]
        if missing(ContactMessage, email):
            ContactMessage.objects.create(
                name="Demo Contact",
                email=email,
                subject="Demo question",
                message="Demo message.",
                consent=True,
            )
            self.created += 1
        if missing(PartnershipEnquiry, email):
            PartnershipEnquiry.objects.create(
                name="Demo Church", email=email, message="Demo enquiry.", consent=True
            )
            self.created += 1
        if missing(Donation, email, "donor_email_hash"):
            Donation.objects.create(
                amount=Decimal("50.00"),
                currency="USD",
                donor_name="Demo Donor",
                donor_email=email,
                transfer_reference="DEMO-REF",
            )
            self.created += 1
        if missing(Subscriber, email):
            Subscriber.objects.create(email=email, name="Demo Reader", status=Subscriber.Status.CONFIRMED)
            self.created += 1
