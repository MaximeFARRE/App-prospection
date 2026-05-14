from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.campaign_state import CampaignState
from app.models.company import Company
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
from app.services.dedupe_service import REVIEW_TAG, merge_contacts, scan_duplicates


# ── Helpers ───────────────────────────────────────────────────────────────────

def _company(db: Session, name: str = "Acme") -> Company:
    c = Company(name=name)
    db.add(c)
    db.flush()
    return c


def _contact(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    email: str,
    company_id: int | None = None,
    **kwargs,
) -> Contact:
    c = Contact(
        first_name=first_name,
        last_name=last_name,
        email=email,
        email_normalized=email.lower(),
        company_id=company_id,
        **kwargs,
    )
    db.add(c)
    db.flush()
    return c


def _message(db: Session, contact_id: int) -> Message:
    m = Message(
        contact_id=contact_id,
        campaign_name="camp",
        subject="Hi",
        body="Body",
        from_email="me@ex.com",
        message_type="intro",
    )
    db.add(m)
    db.flush()
    return m


def _reply(db: Session, contact_id: int) -> Reply:
    r = Reply(
        contact_id=contact_id,
        from_email="them@ex.com",
        received_at=datetime(2024, 6, 1),
    )
    db.add(r)
    db.flush()
    return r


def _campaign_state(db: Session, contact_id: int, campaign_name: str = "camp") -> CampaignState:
    s = CampaignState(contact_id=contact_id, campaign_name=campaign_name)
    db.add(s)
    db.flush()
    return s


# ── scan_duplicates ───────────────────────────────────────────────────────────

class TestScanDuplicates:
    def test_finds_probable_pair_same_name_and_company(self, db: Session):
        co = _company(db)
        _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", company_id=co.id)
        _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com", company_id=co.id)

        result = scan_duplicates(db, mark_probable=False)

        assert len(result.probable_pairs) == 1
        assert result.probable_pairs[0].strategy == "probable"
        assert result.probable_pairs[0].last_name == "Dupont"

    def test_finds_possible_pair_same_last_name_different_first(self, db: Session):
        co = _company(db)
        _contact(db, first_name="Jean", last_name="Dupont", email="jean@ex.com", company_id=co.id)
        _contact(db, first_name="Marie", last_name="Dupont", email="marie@ex.com", company_id=co.id)

        result = scan_duplicates(db, mark_probable=False)

        assert len(result.probable_pairs) == 0
        assert len(result.possible_pairs) == 1
        assert result.possible_pairs[0].strategy == "possible"

    def test_no_duplicates_when_different_companies(self, db: Session):
        co1 = _company(db, "Acme")
        co2 = _company(db, "Beta")
        _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", company_id=co1.id)
        _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com", company_id=co2.id)

        result = scan_duplicates(db, mark_probable=False)

        assert result.probable_pairs == []

    def test_no_duplicates_for_unique_contacts(self, db: Session):
        co = _company(db)
        _contact(db, first_name="Jean", last_name="Dupont", email="jean@ex.com", company_id=co.id)
        _contact(db, first_name="Alice", last_name="Martin", email="alice@ex.com", company_id=co.id)

        result = scan_duplicates(db, mark_probable=False)

        assert result.probable_pairs == []
        assert result.possible_pairs == []

    def test_mark_probable_adds_review_tag_to_notes(self, db: Session):
        co = _company(db)
        c1 = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", company_id=co.id)
        c2 = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com", company_id=co.id)

        result = scan_duplicates(db, mark_probable=True)

        db.refresh(c1)
        db.refresh(c2)
        assert REVIEW_TAG in (c1.notes or "")
        assert REVIEW_TAG in (c2.notes or "")
        assert result.marked_contacts_count == 2

    def test_mark_probable_does_not_add_tag_twice(self, db: Session):
        co = _company(db)
        c1 = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", company_id=co.id)
        _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com", company_id=co.id)

        scan_duplicates(db, mark_probable=True)
        scan_duplicates(db, mark_probable=True)

        db.refresh(c1)
        assert (c1.notes or "").count(REVIEW_TAG) == 1

    def test_suggested_keep_is_more_complete_contact(self, db: Session):
        co = _company(db)
        rich = _contact(
            db, first_name="Jean", last_name="Dupont", email="j1@ex.com",
            company_id=co.id, phone="0600000000", linkedin_url="https://li.com/jean",
        )
        sparse = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com", company_id=co.id)

        result = scan_duplicates(db, mark_probable=False)

        assert result.probable_pairs[0].suggested_keep_contact_id == rich.id


# ── merge_contacts ────────────────────────────────────────────────────────────

class TestMergeContacts:
    def test_raises_when_merging_contact_with_itself(self, db: Session):
        c = _contact(db, first_name="Jean", last_name="Dupont", email="j@ex.com")
        with pytest.raises(ValueError, match="lui-même"):
            merge_contacts(db, c.id, c.id)

    def test_raises_when_contact_not_found(self, db: Session):
        c = _contact(db, first_name="Jean", last_name="Dupont", email="j@ex.com")
        with pytest.raises(ValueError, match="introuvable"):
            merge_contacts(db, c.id, 99999)

    def test_keeps_more_complete_contact(self, db: Session):
        rich = _contact(
            db, first_name="Jean", last_name="Dupont", email="j1@ex.com",
            phone="0600", linkedin_url="https://li.com/jean",
        )
        sparse = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com")

        result = merge_contacts(db, rich.id, sparse.id)

        assert result.kept_contact_id == rich.id
        assert result.removed_contact_id == sparse.id

    def test_fills_missing_fields_from_removed(self, db: Session):
        keeper = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", phone="0600")
        removed = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com", linkedin_url="https://li.com")

        merge_contacts(db, keeper.id, removed.id)

        db.refresh(keeper)
        assert keeper.linkedin_url == "https://li.com"

    def test_transfers_messages_to_keeper(self, db: Session):
        keeper = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", phone="0600")
        removed = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com")
        msg = _message(db, removed.id)

        result = merge_contacts(db, keeper.id, removed.id)

        assert result.transferred_messages == 1
        db.refresh(msg)
        assert msg.contact_id == keeper.id

    def test_transfers_replies_to_keeper(self, db: Session):
        keeper = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", phone="0600")
        removed = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com")
        reply = _reply(db, removed.id)

        result = merge_contacts(db, keeper.id, removed.id)

        assert result.transferred_replies == 1
        db.refresh(reply)
        assert reply.contact_id == keeper.id

    def test_merges_campaign_states_for_same_campaign(self, db: Session):
        keeper = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", phone="0600")
        removed = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com")
        s_keeper = _campaign_state(db, keeper.id, "camp")
        s_keeper.intro_sent = True
        s_removed = _campaign_state(db, removed.id, "camp")
        s_removed.followup_1_sent = True
        db.flush()

        result = merge_contacts(db, keeper.id, removed.id)

        assert result.transferred_campaign_states == 1
        db.refresh(s_keeper)
        assert s_keeper.intro_sent is True
        assert s_keeper.followup_1_sent is True

    def test_transfers_campaign_state_for_different_campaign(self, db: Session):
        keeper = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", phone="0600")
        removed = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com")
        _campaign_state(db, keeper.id, "camp_a")
        s_removed = _campaign_state(db, removed.id, "camp_b")
        db.flush()

        result = merge_contacts(db, keeper.id, removed.id)

        assert result.transferred_campaign_states == 1
        db.refresh(s_removed)
        assert s_removed.contact_id == keeper.id

    def test_removed_contact_deleted_from_db(self, db: Session):
        keeper = _contact(db, first_name="Jean", last_name="Dupont", email="j1@ex.com", phone="0600")
        removed = _contact(db, first_name="Jean", last_name="Dupont", email="j2@ex.com")
        removed_id = removed.id

        merge_contacts(db, keeper.id, removed.id)

        assert db.query(Contact).filter(Contact.id == removed_id).first() is None
