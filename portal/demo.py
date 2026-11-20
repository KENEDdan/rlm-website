"""Fake demo data for every department dashboard (called by ``manage.py seed_demo``; DEBUG only).

Every row carries "DEMO" in a plain-text field (names are encrypted and cannot be searched), so ``reset()``
removes exactly what was created. People's names are obviously fake; phone numbers use +000.
No staff accounts are created here: only the Super Admin creates accounts.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

M = "DEMO"


def _months_ago(n: int, day: int = 10) -> date:
    today = timezone.localdate()
    month = today.month - n
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, min(day, 28))


def seed() -> int:
    from branches.models import Branch
    from communications.models import ContentItem, DesignRequest, EventCoverage
    from development.models import (
        CapitalProposal,
        Contractor,
        MaintenanceRequest,
        Milestone,
        Project,
        ProjectExpense,
        ProjectRisk,
        Property,
        SiteVisit,
    )
    from discipleship.models import Assessment, Cohort, Curriculum, Enrollment, Registration
    from events.models import Event
    from finance.models import (
        BudgetLine,
        Donor,
        FinanceVolunteer,
        GrantOpportunity,
        LedgerEntry,
        Pledge,
        Proposal,
    )
    from logistics.models import (
        AssetLoan,
        InventoryItem,
        LogisticsPlan,
        LogisticsTask,
        PurchaseRequest,
        Quotation,
        Supplier,
    )
    from membership.models import Activity, Announcement, Attendance, Member, WelfareCase
    from missions.models import Campaign, Community, FieldReport, NewConvert, Team, TeamMember
    from portal.models import Department

    if Member.objects.filter(city__startswith=M).exists():
        return 0
    rng = random.Random(16)  # noqa: S311  # nosec B311 - deterministic FAKE demo data, not security
    today = timezone.localdate()
    year = today.year
    branches = list(Branch.objects.filter(slug__in=["juba", "yei"]))
    depts = {d.code: d for d in Department.objects.all()}
    count = 0

    # ---------------------------------------------------------------- membership
    statuses = (
        ["active"] * 14
        + ["integration"] * 3
        + ["orientation"] * 2
        + ["submitted"] * 3
        + ["under_review", "inactive", "rejected"]
    )
    members = []
    for i, status in enumerate(statuses):
        joined = (
            _months_ago(rng.randint(0, 11), rng.randint(1, 28))
            if status not in ("submitted", "under_review", "rejected")
            else None
        )
        age = rng.choice([16, 22, 24, 29, 33, 38, 45, 52, 61])
        member = Member.objects.create(
            full_name=f"Demo Member {i + 1}",
            gender=rng.choice(["female", "male"]),
            date_of_birth=today.replace(year=today.year - age, day=1).isoformat(),
            nationality="South Sudanese",
            country="South Sudan",
            city=f"{M} Town",
            branch=rng.choice(branches),
            phone=f"+000 900 000 {i:03d}",
            email=f"member{i + 1}@example.test",
            status=status,
            join_date=joined,
            source="website",
            born_again="yes",
            testimony="Demo testimony.",
            comms_opt_in=age >= 18 and i % 3 != 0,
            consent=True,
            declaration=True,
            guardian_name="Demo Guardian" if age < 18 else "",
            guardian_contact="+000 1" if age < 18 else "",
            guardian_consent=age < 18,
        )
        members.append(member)
    count += len(members)
    active = [m for m in members if m.status == "active"]
    for n in range(8):
        for branch in branches:
            activity = Activity.objects.create(
                name=f"{M} Sunday service", kind="service", branch=branch, date=today - timedelta(days=7 * n)
            )
            for m in active:
                if m.branch_id == branch.pk:
                    Attendance.objects.create(activity=activity, member=m, present=rng.random() < 0.7)
    from membership.services import recompute_engagement

    for m in active:
        recompute_engagement(m)
    WelfareCase.objects.create(
        member=active[0],
        category="medical",
        summary="Demo: hospital bill support.",
        opened_on=today - timedelta(days=20),
    )
    WelfareCase.objects.create(
        member=active[1], category="bereavement", summary="Demo: family loss.", status="closed"
    )
    Announcement.objects.create(title=f"{M} Annual members' meeting", body="Demo announcement.")
    count += 3

    # ---------------------------------------------------------------- finance
    lines = {}
    for code, amount in (
        ("membership", 3000),
        ("logistics", 12000),
        ("media", 4000),
        ("missions", 15000),
        ("discipleship", 5000),
        ("development", 60000),
    ):
        lines[code] = BudgetLine.objects.create(
            year=year,
            department=depts[code],
            category="programmes",
            name=f"{M} {depts[code].name} operations",
            amount=amount,
            status="approved",  # demo budgets count as approved by the executive
        )
    for n in range(12):
        day = _months_ago(n, rng.randint(1, 28))
        LedgerEntry.objects.create(
            kind="income",
            date=day,
            amount=Decimal(rng.randint(1500, 4500)),
            income_source=rng.choice(["offering", "donation", "church", "grant"]),
            description=f"{M} income {day:%b}",
            status="posted",
            number=f"IN-D-{n:02d}",
            posted_at=timezone.now(),
        )
        for code in ("missions", "media", "logistics"):
            if day.year == year:
                LedgerEntry.objects.create(
                    kind="expense",
                    date=day,
                    amount=Decimal(rng.randint(200, 1400)),
                    category="programmes",
                    department=depts[code],
                    budget_line=lines[code],
                    description=f"{M} {code} spend {day:%b}",
                    status="posted",
                    number=f"EX-D-{code[:3]}-{n:02d}",
                    posted_at=timezone.now(),
                )
    LedgerEntry.objects.create(
        kind="expense",
        amount=Decimal("380"),
        category="travel",
        department=depts["missions"],
        budget_line=lines["missions"],
        description=f"{M} fuel for crusade",
        status="submitted",
        submitted_at=timezone.now(),
    )
    donors = []
    for i, (kind, stage) in enumerate(
        [
            ("church", "committed"),
            ("individual", "received"),
            ("organisation", "proposal"),
            ("grant_maker", "contacted"),
            ("ministry", "prospect"),
            ("individual", "lapsed"),
        ]
    ):
        donors.append(
            Donor.objects.create(
                kind=kind,
                name=f"Demo Partner {i + 1}",
                country=f"{M} Country",
                stage=stage,
                next_step="Demo follow-up call",
                next_step_due=today + timedelta(days=i * 5 - 6),
            )
        )
    Pledge.objects.create(
        donor=donors[0],
        amount=Decimal("5000"),
        received_amount=Decimal("2000"),
        purpose=f"{M} youth conference",
        expected_by=today + timedelta(days=30),
    )
    Pledge.objects.create(
        donor=donors[1],
        amount=Decimal("1200"),
        received_amount=Decimal("0"),
        purpose=f"{M} Bibles",
        expected_by=today - timedelta(days=10),
    )
    GrantOpportunity.objects.create(
        funder="Demo Foundation",
        title=f"{M} Youth leadership grant",
        amount=Decimal("20000"),
        deadline=today + timedelta(days=18),
        status="drafting",
    )
    Proposal.objects.create(
        kind="appeal",
        title=f"{M} Christmas outreach appeal",
        status="sent",
        sent_on=today - timedelta(days=12),
        donor=donors[2],
    )
    FinanceVolunteer.objects.create(
        full_name="Demo Volunteer Accountant",
        email="finvol@example.test",
        phone="+000 1",
        education_level="Degree",
        field_of_study=f"{M} Accounting",
        finance_experience="yes",
        statement="Demo.",
        willing_integrity="yes",
        declaration=True,
        consent=True,
    )
    count += 30

    # ---------------------------------------------------------------- logistics
    suppliers = [
        Supplier.objects.create(name=f"{M} Supplier {c}", category=c, rating=r)
        for c, r in (("Printing", 4), ("Sound", 5), ("Transport", 3))
    ]
    for i, status in enumerate(["submitted", "recommended", "budget_confirmed", "approved", "closed"]):
        pr = PurchaseRequest.objects.create(
            title=f"{M} purchase {i + 1}",
            requesting_department=depts[rng.choice(["media", "missions", "membership"])],
            description="Demo request",
            status=status,
            number=f"PR-DEMO-{i:03d}",
            estimated_cost=Decimal(300 + i * 150),
        )
        for s in suppliers[: 3 if status != "submitted" else 1]:
            Quotation.objects.create(
                request=pr,
                supplier=s,
                amount=Decimal(rng.randint(250, 600)),
                delivery_days=rng.randint(2, 10),
            )
    InventoryItem.objects.create(
        name=f"{M} A4 paper",
        kind="consumable",
        quantity=3,
        unit="reams",
        reorder_level=10,
        location="Juba office",
    )
    mixer = InventoryItem.objects.create(
        name=f"{M} Sound mixer",
        kind="asset",
        quantity=1,
        tag="RLM-0001",
        location="Juba store",
        maintenance_interval_days=90,
        last_maintenance=today - timedelta(days=100),
    )
    InventoryItem.objects.create(name=f"{M} Plastic chairs", kind="asset", quantity=150, location="Juba hall")
    AssetLoan.objects.create(item=mixer, borrower="Demo youth team", due_back=today - timedelta(days=2))
    upcoming = Event.objects.filter(start__gte=timezone.now()).first()
    plan = LogisticsPlan.objects.create(
        title=f"{M} Youth conference logistics",
        kind="conference",
        event=upcoming,
        start_date=today + timedelta(days=21),
        location="Juba",
        expected_attendance=400,
    )
    for cat, desc, done in (
        ("transport", "2 buses from Yei", True),
        ("accommodation", "Hostel for 60", False),
        ("feeding", "Meals for 400 x 3 days", False),
        ("equipment", "Stage sound", True),
    ):
        LogisticsTask.objects.create(plan=plan, category=cat, description=desc, done=done)
    count += 15

    # ---------------------------------------------------------------- missions
    communities = [
        Community.objects.create(name=f"{M} {n}", kind=k, region=r, branch=b, status=s)
        for n, k, r, b, s in (
            ("Gudele", "community", "Central Equatoria", branches[0], "engaged"),
            ("Yei Prison", "prison", "Central Equatoria", branches[-1], "engaged"),
            ("Kator Secondary", "school", "Central Equatoria", branches[0], "target"),
        )
    ]
    team = Team.objects.create(name=f"{M} Juba evangelism team", branch=branches[0], focus="Open-air")
    for i in range(4):
        TeamMember.objects.create(
            team=team, name=f"Demo Evangelist {i + 1}", role=rng.choice(["Preacher", "Counsellor", "Worship"])
        )
    for n in range(10):
        community = rng.choice(communities)
        start = _months_ago(n, 6)
        campaign = Campaign.objects.create(
            title=f"{M} outreach {start:%b %Y}",
            kind=rng.choice(["crusade", "open_air", "school", "prison"]),
            community=community,
            location=community.name.replace(f"{M} ", ""),
            branch=community.branch,
            start_date=start,
            team=team,
            status="completed",
        )
        decisions = rng.randint(5, 40)
        FieldReport.objects.create(
            campaign=campaign,
            report_date=start,
            souls_reached=rng.randint(80, 600),
            decisions=decisions,
            challenges="Demo: rain.",
        )
        for j in range(min(decisions, 3)):
            NewConvert.objects.create(
                campaign=campaign,
                decision_date=start,
                full_name=f"Demo Convert {n}-{j}",
                phone="+000 2",
                age_band=rng.choice(["18_25", "26_35", "36_50"]),
                location=f"{M} village",
                consent_to_contact=True,
            )
    Campaign.objects.create(
        title=f"{M} Christmas crusade",
        kind="crusade",
        community=communities[0],
        branch=branches[0],
        start_date=today + timedelta(days=30),
        status="approved",
    )
    count += 40

    # ---------------------------------------------------------------- discipleship
    curriculum = Curriculum.objects.create(title=f"{M} Foundations of faith", level="Foundations")
    cohort = Cohort.objects.create(
        name=f"{M} Foundations Juba",
        branch=branches[0],
        curriculum=curriculum,
        start_date=today - timedelta(days=40),
        status="running",
        schedule="Saturdays 4-6 pm",
    )
    from discipleship.models import FollowUp
    from discipleship.services import _disciple_from_convert

    for k, follow in enumerate(
        FollowUp.objects.filter(convert__location__startswith=M).order_by("convert__decision_date")
    ):
        if k % 3 == 0:
            disciple = _disciple_from_convert(follow.convert)
            follow.disciple, follow.status = disciple, "enrolled"
            follow.save()
            Enrollment.objects.create(
                cohort=cohort, disciple=disciple, status=rng.choice(["enrolled", "completed", "enrolled"])
            )
            Assessment.objects.create(disciple=disciple, **{a: rng.randint(2, 5) for a in Assessment.AREAS})
        elif k % 3 == 1:
            follow.status = "contacted"
            follow.save()
    for i in range(3):
        Registration.objects.create(
            full_name=f"Demo Disciple {i}",
            age=str(20 + i),
            phone="+000 3",
            born_again="yes",
            baptized="no",
            attends_church="yes",
            journey="Demo.",
            growth_areas=["knowledge", "prayer"][: i + 1],
            city=f"{M} Town",
            consent=True,
        )
    count += 10

    # ---------------------------------------------------------------- media
    for n in range(18):
        planned = today - timedelta(days=n * 9)
        ContentItem.objects.create(
            title=f"{M} post {n + 1}",
            channel=rng.choice(["facebook", "instagram", "youtube", "website", "tiktok"]),
            stage="published" if n > 2 else rng.choice(["idea", "production", "review"]),
            planned_date=planned,
            published_on=planned if n > 2 else None,
        )
    DesignRequest.objects.create(
        title=f"{M} Crusade poster",
        kind="poster",
        requesting_department=depts["missions"],
        needed_by=today + timedelta(days=5),
        brief="A3",
    )
    DesignRequest.objects.create(
        title=f"{M} Membership banner",
        kind="banner",
        requesting_department=depts["membership"],
        needed_by=today - timedelta(days=2),
        brief="Roll-up",
        status="in_progress",
    )
    if upcoming and not EventCoverage.objects.filter(event=upcoming).exists():
        EventCoverage.objects.create(event=upcoming, live_stream=True)
    count += 21

    # ---------------------------------------------------------------- development
    plot = Property.objects.create(
        name=f"{M} Juba plot", kind="land", location="Juba, Gudele", branch=branches[0], tenure="owned"
    )
    office = Property.objects.create(
        name=f"{M} Yei office", kind="building", location="Yei town", branch=branches[-1], tenure="leased"
    )
    builder = Contractor.objects.create(
        name=f"{M} Builders Ltd", kind="contractor", specialty="Masonry", rating=4
    )
    hall = Project.objects.create(
        name=f"{M} Juba conference hall",
        kind="hall",
        phase="construction",
        site=plot,
        branch=branches[0],
        budget=Decimal("120000"),
        funding_secured=Decimal("70000"),
        start_date=today - timedelta(days=150),
        target_end=today + timedelta(days=200),
    )
    hall.contractors.add(builder)
    hostel = Project.objects.create(
        name=f"{M} Youth hostel",
        kind="hostel",
        phase="design",
        budget=Decimal("80000"),
        funding_secured=Decimal("10000"),
        start_date=today - timedelta(days=30),
        target_end=today + timedelta(days=400),
    )
    Project.objects.create(
        name=f"{M} Training centre",
        kind="training",
        phase="fundraising",
        budget=Decimal("150000"),
        start_date=today + timedelta(days=60),
        target_end=today + timedelta(days=700),
    )
    for title, due, done in (("Foundation", -90, True), ("Walls", -20, False), ("Roof", 60, False)):
        Milestone.objects.create(
            project=hall,
            title=title,
            due_date=today + timedelta(days=due),
            completed_on=today + timedelta(days=due) if done else None,
        )
    ProjectExpense.objects.create(project=hall, description=f"{M} cement and sand", amount=Decimal("38000"))
    ProjectExpense.objects.create(project=hostel, description=f"{M} architect fees", amount=Decimal("4500"))
    SiteVisit.objects.create(
        project=hall,
        date=today - timedelta(days=12),
        progress_percent=40,
        summary="Demo: walls at window level.",
    )
    ProjectRisk.objects.create(project=hall, description="Demo: cement price rises", severity="high")
    MaintenanceRequest.objects.create(site=office, title=f"{M} Leaking roof", priority="urgent")
    MaintenanceRequest.objects.create(
        site=office,
        title=f"{M} Generator service",
        priority="medium",
        status="scheduled",
        scheduled_for=today + timedelta(days=7),
    )
    CapitalProposal.objects.create(
        project=hostel, title=f"{M} Youth hostel phase 1", amount=Decimal("70000"), summary="Demo summary."
    )
    count += 16
    return count


def reset() -> int:
    from communications.models import ContentItem, DesignRequest
    from development.models import Contractor, Project, Property
    from discipleship.models import Cohort, Curriculum, Disciple, Registration
    from finance.models import BudgetLine, Donor, FinanceVolunteer, GrantOpportunity, LedgerEntry, Proposal
    from logistics.models import InventoryItem, LogisticsPlan, PurchaseRequest, Supplier
    from membership.models import Activity, Announcement, Member
    from missions.models import Campaign, Community, NewConvert, Team

    total = 0
    total += Disciple.objects.filter(
        Q(convert__location__startswith=M) | Q(registration__city__startswith=M)
    ).delete()[0]
    for model, field in (
        (NewConvert, "location"),
        (Campaign, "title"),
        (Community, "name"),
        (Team, "name"),
        (Registration, "city"),
        (Cohort, "name"),
        (Curriculum, "title"),
        (Activity, "name"),
        (Announcement, "title"),
        (Member, "city"),
        (Donor, "country"),
        (GrantOpportunity, "title"),
        (Proposal, "title"),
        (FinanceVolunteer, "field_of_study"),
        (PurchaseRequest, "title"),
        (Supplier, "name"),
        (InventoryItem, "name"),
        (LogisticsPlan, "title"),
        (ContentItem, "title"),
        (DesignRequest, "title"),
        (Project, "name"),
        (Property, "name"),
        (Contractor, "name"),
    ):
        total += model.objects.filter(**{f"{field}__startswith": M}).delete()[0]
    # Posted ledger rows are immutable by design; demo rows are removed with a raw queryset delete on purpose.
    total += LedgerEntry.objects.filter(description__startswith=M)._raw_delete(LedgerEntry.objects.db)
    total += BudgetLine.objects.filter(name__startswith=M).delete()[0]
    return total
