from __future__ import annotations

from datetime import datetime

import pytest

from app.models.campaign_state import CampaignState
from app.models.contact import Contact
from app.services.dedupe_utils import (
    completeness_score,
    merge_campaign_state,
    merge_contact_fields,
    merge_notes,
    merge_sentiment,
    min_dt,
    norm,
    select_keeper,
)


def _contact(**kwargs) -> Contact:
    c = Contact()
    for field, value in kwargs.items():
        setattr(c, field, value)
    return c


def _state(**kwargs) -> CampaignState:
    s = CampaignState()
    s.intro_sent = False
    s.followup_1_sent = False
    s.followup_2_sent = False
    s.has_replied = False
    s.intro_sent_at = None
    s.followup_1_sent_at = None
    s.followup_2_sent_at = None
    s.reply_sentiment = None
    for field, value in kwargs.items():
        setattr(s, field, value)
    return s


# ── norm ──────────────────────────────────────────────────────────────────────

class TestNorm:
    def test_none_returns_empty(self):
        assert norm(None) == ""

    def test_strips_whitespace_and_lowercases(self):
        assert norm("  Hello World  ") == "hello world"

    def test_empty_string_returns_empty(self):
        assert norm("") == ""

    def test_already_lowercase(self):
        assert norm("jean") == "jean"


# ── completeness_score ────────────────────────────────────────────────────────

class TestCompletenessScore:
    def test_empty_contact_scores_zero(self):
        assert completeness_score(_contact()) == 0

    def test_one_field_scores_one(self):
        assert completeness_score(_contact(first_name="Jean")) == 1

    def test_three_fields_scores_three(self):
        c = _contact(first_name="Jean", last_name="Dupont", email="j@ex.com")
        assert completeness_score(c) == 3

    def test_empty_string_does_not_count(self):
        assert completeness_score(_contact(first_name="")) == 0


# ── select_keeper ─────────────────────────────────────────────────────────────

class TestSelectKeeper:
    def test_more_complete_contact_is_keeper(self):
        rich = _contact(id=2, first_name="Jean", last_name="Dupont", email="j@ex.com")
        sparse = _contact(id=1, first_name="Jean")
        keeper, removed = select_keeper(rich, sparse)
        assert keeper is rich
        assert removed is sparse

    def test_older_created_at_wins_on_equal_score(self):
        old = _contact(id=2, first_name="Jean", created_at=datetime(2024, 1, 1))
        new = _contact(id=1, first_name="Jean", created_at=datetime(2024, 6, 1))
        keeper, _ = select_keeper(old, new)
        assert keeper is old

    def test_lower_id_wins_when_score_and_date_are_tied(self):
        a = _contact(id=1, first_name="Jean")
        b = _contact(id=2, first_name="Jean")
        keeper, _ = select_keeper(a, b)
        assert keeper is a

    def test_symmetric_result(self):
        a = _contact(id=1, first_name="Jean", last_name="Dupont")
        b = _contact(id=2, first_name="Jean")
        k1, r1 = select_keeper(a, b)
        k2, r2 = select_keeper(b, a)
        assert k1 is k2
        assert r1 is r2


# ── merge_contact_fields ──────────────────────────────────────────────────────

class TestMergeContactFields:
    def test_fills_missing_field_from_removed(self):
        keeper = _contact(first_name="Jean")
        removed = _contact(last_name="Dupont", phone="0600000000")
        merge_contact_fields(keeper, removed)
        assert keeper.last_name == "Dupont"
        assert keeper.phone == "0600000000"

    def test_does_not_overwrite_existing_field(self):
        keeper = _contact(last_name="Martin")
        removed = _contact(last_name="Dupont")
        merge_contact_fields(keeper, removed)
        assert keeper.last_name == "Martin"

    def test_fills_email_when_keeper_has_none(self):
        keeper = _contact()
        removed = _contact(email="jean@ex.com", email_normalized="jean@ex.com")
        merge_contact_fields(keeper, removed)
        assert keeper.email == "jean@ex.com"


# ── merge_notes ───────────────────────────────────────────────────────────────

class TestMergeNotes:
    def test_both_none_returns_none(self):
        assert merge_notes(None, None) is None

    def test_only_keeper_returns_keeper(self):
        assert merge_notes("Note A", None) == "Note A"

    def test_only_removed_returns_removed(self):
        assert merge_notes(None, "Note B") == "Note B"

    def test_both_present_joined_with_separator(self):
        result = merge_notes("Note A", "Note B")
        assert "Note A" in result
        assert "Note B" in result
        assert "---" in result

    def test_duplicate_content_not_repeated(self):
        result = merge_notes("Same", "Same")
        assert result.count("Same") == 1

    def test_empty_string_treated_as_none(self):
        assert merge_notes("", "Note") == "Note"


# ── merge_sentiment ───────────────────────────────────────────────────────────

class TestMergeSentiment:
    def test_positive_beats_negative(self):
        assert merge_sentiment("positive", "negative") == "positive"

    def test_negative_beats_neutral(self):
        assert merge_sentiment("negative", "neutral") == "negative"

    def test_neutral_beats_auto(self):
        assert merge_sentiment("neutral", "auto") == "neutral"

    def test_any_value_beats_none(self):
        assert merge_sentiment(None, "unknown") == "unknown"

    def test_equal_priority_keeps_existing(self):
        assert merge_sentiment("neutral", "neutral") == "neutral"

    def test_incoming_positive_wins_over_none(self):
        assert merge_sentiment(None, "positive") == "positive"


# ── min_dt ────────────────────────────────────────────────────────────────────

class TestMinDt:
    def test_both_none_returns_none(self):
        assert min_dt(None, None) is None

    def test_left_none_returns_right(self):
        dt = datetime(2024, 3, 15)
        assert min_dt(None, dt) == dt

    def test_right_none_returns_left(self):
        dt = datetime(2024, 3, 15)
        assert min_dt(dt, None) == dt

    def test_returns_earlier_date(self):
        early = datetime(2024, 1, 1)
        late = datetime(2024, 12, 31)
        assert min_dt(early, late) == early
        assert min_dt(late, early) == early

    def test_equal_dates_returns_either(self):
        dt = datetime(2024, 6, 1)
        assert min_dt(dt, dt) == dt


# ── merge_campaign_state ──────────────────────────────────────────────────────

class TestMergeCampaignState:
    def test_booleans_are_ored(self):
        existing = _state(intro_sent=True, followup_1_sent=False)
        incoming = _state(intro_sent=False, followup_1_sent=True)
        merge_campaign_state(existing, incoming)
        assert existing.intro_sent is True
        assert existing.followup_1_sent is True

    def test_has_replied_is_ored(self):
        existing = _state(has_replied=False)
        incoming = _state(has_replied=True)
        merge_campaign_state(existing, incoming)
        assert existing.has_replied is True

    def test_timestamps_take_earliest(self):
        early = datetime(2024, 1, 1)
        late = datetime(2024, 12, 31)
        existing = _state(intro_sent_at=late)
        incoming = _state(intro_sent_at=early)
        merge_campaign_state(existing, incoming)
        assert existing.intro_sent_at == early

    def test_sentiment_follows_priority(self):
        existing = _state(reply_sentiment="neutral")
        incoming = _state(reply_sentiment="positive")
        merge_campaign_state(existing, incoming)
        assert existing.reply_sentiment == "positive"

    def test_none_timestamp_filled_by_incoming(self):
        dt = datetime(2024, 6, 1)
        existing = _state(followup_1_sent_at=None)
        incoming = _state(followup_1_sent_at=dt)
        merge_campaign_state(existing, incoming)
        assert existing.followup_1_sent_at == dt
