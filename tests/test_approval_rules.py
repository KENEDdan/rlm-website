"""Refusal paths of the two-person rules (Vision/Mission changes and bank details), tested at service level."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import RequestFactory

from accounts import reauth
from accounts.roles import FINANCE, TECHNICAL
from core import vision_mission as vm
from core.models import ContentChangeRequest, SiteContent, SiteSettings
from giving import bank_details as bank
from giving.models import BankDetailChange, GivingSettings

pytestmark = pytest.mark.django_db


def _request(user: Any, fresh: bool = False) -> Any:
    request = RequestFactory().post("/")
    request.user = user
    request.session = {}
    if fresh:
        reauth.mark_fresh(request)
    return request


# ------------------------------------------------------------------ Vision and Mission
def test_draft_rules(make_staff: Any) -> None:
    tech = make_staff(TECHNICAL)
    req = _request(tech)
    with pytest.raises(vm.ChangeError):
        vm.create_draft(req, "vision", "   ")
    with pytest.raises(vm.ChangeError):
        vm.create_draft(req, "footer", "x")
    with pytest.raises(vm.ChangeError):
        vm.create_draft(req, "vision", SiteContent.load().vision)  # already published
    with pytest.raises(vm.ChangeError):
        vm.create_draft(_request(make_staff(FINANCE)), "vision", "Not allowed")


def test_only_the_author_edits_submits_and_withdraws(make_staff: Any) -> None:
    author, other = make_staff(TECHNICAL), make_staff(TECHNICAL)
    change = vm.create_draft(_request(author), "mission", "Draft mission")
    with pytest.raises(vm.ChangeError):
        vm.update_draft(_request(other), change, "Hijacked", "")
    vm.update_draft(_request(author), change, "Better mission", "clearer")
    change.refresh_from_db()
    assert change.text == "Better mission" and change.reason == "clearer"
    with pytest.raises(vm.ChangeError):
        vm.submit(_request(other), change)
    with pytest.raises(vm.ChangeError):
        vm.withdraw(_request(other), change)
    vm.withdraw(_request(author), change)
    change.refresh_from_db()
    assert change.status == "withdrawn"
    with pytest.raises(vm.ChangeError):
        vm.withdraw(_request(author), change)


def test_decisions_need_an_approver_a_submitted_change_and_reauth(make_staff: Any) -> None:
    author = make_staff(TECHNICAL)
    admin = make_staff(superuser=True)
    change = vm.create_draft(_request(author), "vision", "Proposed vision")
    with pytest.raises(vm.ChangeError):
        vm.approve(_request(admin, fresh=True), change)  # still a draft
    vm.submit(_request(author), change)
    with pytest.raises(vm.ChangeError):
        vm.approve(_request(make_staff(TECHNICAL), fresh=True), change)  # not an approver
    with pytest.raises(reauth.ReauthRequired):
        vm.approve(_request(admin), change)
    with pytest.raises(vm.ChangeError):
        vm.publish(_request(author), change)  # not approved yet
    vm.approve(_request(admin, fresh=True), change)
    with pytest.raises(vm.ChangeError):
        vm.publish(_request(make_staff(TECHNICAL)), change)  # neither author nor approver
    vm.publish(_request(admin), change)
    assert SiteContent.load().vision == "Proposed vision"


def test_approver_cannot_approve_own_change(make_staff: Any) -> None:
    admin = make_staff(superuser=True)
    change = vm.create_draft(_request(admin), "vision", "Own change")
    vm.submit(_request(admin), change)
    with pytest.raises(vm.ChangeError):
        vm.approve(_request(admin, fresh=True), change)


def test_rollback_rules(make_staff: Any) -> None:
    tech = make_staff(TECHNICAL)
    current = vm.history("vision").first()
    with pytest.raises(vm.ChangeError):
        vm.rollback(_request(tech), current)  # already the published text
    draft = vm.create_draft(_request(tech), "vision", "Some draft")
    with pytest.raises(vm.ChangeError):
        vm.rollback(_request(tech), draft)  # not a published version
    SiteSettings.objects.update(vision_mission_approval_required=False)
    published = vm.create_draft(_request(tech), "vision", "Short-lived")
    vm.publish(_request(tech), published)
    change = vm.rollback(_request(tech), current)  # rule off: published straight away
    assert change.status == "published" and SiteContent.load().vision == current.text
    assert not ContentChangeRequest.objects.filter(status__in=["draft", "submitted", "approved"]).exists()


def test_executive_director_role_window(make_staff: Any) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from accounts.roles import EXECUTIVE
    from finance.models import Approver

    user = make_staff(EXECUTIVE)
    assert not vm.is_approver(user)
    row = Approver.objects.create(
        user=user, role="executive_director", ends_on=timezone.localdate() - timedelta(days=1)
    )
    assert not vm.is_approver(user)  # appointment ended
    row.ends_on = None
    row.save()
    assert vm.is_approver(user)
    Approver.objects.create(user=make_staff(EXECUTIVE), role="acting")
    assert not vm.is_approver(Approver.objects.get(role="acting").user)  # acting approvers: expenditure only


# ------------------------------------------------------------------ bank details
DATA = dict.fromkeys(
    ("account_name", "bank_name", "account_number", "swift_code", "branch_name", "currency"), ""
)
DATA.update(account_name="RLM", bank_name="Bank", account_number="12345678", bank_transfer_enabled=True)


def test_bank_propose_rules(make_staff: Any) -> None:
    head = make_staff(FINANCE, heads={"finance"})
    with pytest.raises(bank.BankChangeError):
        bank.propose(_request(make_staff(FINANCE), fresh=True), DATA, "x")  # ordinary member
    with pytest.raises(reauth.ReauthRequired):
        bank.propose(_request(head), DATA, "x")
    with pytest.raises(bank.BankChangeError):
        bank.propose(_request(head, fresh=True), DATA, " ")  # reason required
    current = {f: getattr(GivingSettings.load(), f) for f in DATA}
    with pytest.raises(bank.BankChangeError):
        bank.propose(_request(head, fresh=True), current, "same")  # nothing changed
    bank.propose(_request(head, fresh=True), DATA, "new account")
    with pytest.raises(bank.BankChangeError):
        bank.propose(_request(head, fresh=True), DATA, "again")  # one pending at a time


def test_bank_reject_and_confirm_rules(make_staff: Any) -> None:
    head = make_staff(FINANCE, heads={"finance"})
    founder = make_staff(superuser=True)
    change = bank.propose(_request(head, fresh=True), DATA, "new account")
    with pytest.raises(bank.BankChangeError):
        bank.reject(_request(head, fresh=True), change, "no")  # not a confirmer
    with pytest.raises(reauth.ReauthRequired):
        bank.reject(_request(founder), change, "no")
    with pytest.raises(bank.BankChangeError):
        bank.reject(_request(founder, fresh=True), change, " ")  # reason required
    with pytest.raises(bank.BankChangeError):
        bank.cancel(_request(make_staff(FINANCE, heads={"finance"})), change)  # someone else's change
    bank.reject(_request(founder, fresh=True), change, "Account not verified with the bank")
    change.refresh_from_db()
    assert change.status == "rejected" and GivingSettings.load().account_number == ""
    with pytest.raises(bank.BankChangeError):
        bank.confirm(_request(founder, fresh=True), change)  # no longer pending
    with pytest.raises(bank.BankChangeError):
        bank.cancel(_request(head), change)
    assert BankDetailChange.objects.count() == 1


def test_super_admin_cannot_confirm_own_proposal(make_staff: Any) -> None:
    admin = make_staff(superuser=True)
    change = bank.propose(_request(admin, fresh=True), DATA, "set up")
    with pytest.raises(bank.BankChangeError):
        bank.confirm(_request(admin, fresh=True), change)
    bank.confirm(_request(make_staff(superuser=True), fresh=True), change)
    assert GivingSettings.load().account_number == "12345678"
