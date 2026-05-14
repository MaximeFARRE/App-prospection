from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.campaign_state import CampaignState
from app.models.contact import Contact
from app.models.reply import Reply
from app.services.reply_classification_service import (
    ReplyCandidate,
    classify_sentiment,
    record_classified_reply,
    update_reply_sentiment,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _contact(db: Session, email: str = "c@ex.com") -> Contact:
    c = Contact(email=email, email_normalized=email.lower())
    db.add(c)
    db.flush()
    return c


def _candidate(contact_id: int, body: str | None, campaign_name: str | None = None) -> ReplyCandidate:
    return ReplyCandidate(
        contact_id=contact_id,
        in_reply_to_message_id=None,
        subject="Re: hello",
        body=body,
        from_email="them@ex.com",
        gmail_thread_id="thread_1",
        received_at=datetime(2024, 6, 1, 10, 0),
        campaign_name=campaign_name,
    )


# ── classify_sentiment ────────────────────────────────────────────────────────

class TestClassifySentiment:
    def test_none_body_returns_neutral(self):
        assert classify_sentiment(None) == "neutral"

    def test_empty_body_returns_neutral(self):
        assert classify_sentiment("") == "neutral"

    def test_negative_keyword_non(self):
        assert classify_sentiment("non merci") == "negative"

    def test_negative_keyword_stop(self):
        assert classify_sentiment("stop") == "negative"

    def test_negative_keyword_unsubscribe(self):
        assert classify_sentiment("please unsubscribe me") == "negative"

    def test_negative_beats_positive_when_both_present(self):
        # "pas interesse" contains a negative keyword
        assert classify_sentiment("pas interesse, merci") == "negative"

    def test_positive_keyword_interesse(self):
        assert classify_sentiment("je suis interesse par votre profil") == "positive"

    def test_positive_keyword_oui(self):
        assert classify_sentiment("oui, appelez-moi") == "positive"

    def test_positive_keyword_volontiers(self):
        assert classify_sentiment("volontiers, on peut se parler") == "positive"

    def test_accented_positive_keyword_normalized(self):
        # "intéressé" → after normalize → "interesse"
        assert classify_sentiment("je suis intéressé") == "positive"

    def test_accented_negative_keyword_normalized(self):
        assert classify_sentiment("pas intéressée merci") == "negative"

    def test_unknown_text_returns_neutral(self):
        assert classify_sentiment("Bonjour, merci pour votre message.") == "neutral"

    def test_case_insensitive(self):
        assert classify_sentiment("NON merci") == "negative"
        assert classify_sentiment("OUI avec plaisir") == "positive"


# ── record_classified_reply ───────────────────────────────────────────────────

class TestRecordClassifiedReply:
    def test_creates_new_reply(self, db: Session):
        contact = _contact(db)
        candidate = _candidate(contact.id, "oui cela m'interesse")

        result = record_classified_reply(candidate, db)

        assert result.created is True
        assert result.sentiment == "positive"
        assert db.query(Reply).filter(Reply.id == result.reply_id).first() is not None

    def test_does_not_duplicate_existing_reply(self, db: Session):
        contact = _contact(db)
        candidate = _candidate(contact.id, "oui")

        result1 = record_classified_reply(candidate, db)
        result2 = record_classified_reply(candidate, db)

        assert result1.created is True
        assert result2.created is False
        assert result1.reply_id == result2.reply_id

    def test_creates_campaign_state_when_campaign_specified(self, db: Session):
        contact = _contact(db)
        candidate = _candidate(contact.id, "non", campaign_name="camp_2024")

        result = record_classified_reply(candidate, db)

        state = db.query(CampaignState).filter(
            CampaignState.contact_id == contact.id,
            CampaignState.campaign_name == "camp_2024",
        ).first()
        assert state is not None
        assert state.has_replied is True
        assert state.reply_sentiment == "negative"
        assert result.updated_campaign_states == 1

    def test_updates_existing_campaign_state(self, db: Session):
        contact = _contact(db, email="updates_existing@ex.com")
        state = CampaignState(contact_id=contact.id, campaign_name="camp")
        db.add(state)
        db.flush()
        candidate = _candidate(contact.id, "oui", campaign_name="camp")

        record_classified_reply(candidate, db)

        assert state.has_replied is True
        assert state.reply_sentiment == "positive"

    def test_updates_all_campaign_states_when_no_campaign_name(self, db: Session):
        contact = _contact(db, email="updates_all@ex.com")
        s1 = CampaignState(contact_id=contact.id, campaign_name="camp_a")
        s2 = CampaignState(contact_id=contact.id, campaign_name="camp_b")
        db.add_all([s1, s2])
        db.flush()
        candidate = _candidate(contact.id, "non", campaign_name=None)

        result = record_classified_reply(candidate, db)

        assert result.updated_campaign_states == 2
        assert s1.has_replied is True
        assert s2.has_replied is True


# ── update_reply_sentiment ────────────────────────────────────────────────────

class TestUpdateReplySentiment:
    def _make_reply(self, db: Session, email: str = "make_reply@ex.com") -> Reply:
        contact = _contact(db, email=email)
        reply = Reply(
            contact_id=contact.id,
            from_email="them@ex.com",
            sentiment="neutral",
            received_at=datetime(2024, 6, 1),
        )
        db.add(reply)
        db.flush()
        return reply

    def test_updates_sentiment_on_existing_reply(self, db: Session):
        reply = self._make_reply(db)

        result = update_reply_sentiment(reply.id, "positive", db)

        assert result.sentiment == "positive"
        assert reply.sentiment == "positive"

    def test_raises_on_invalid_sentiment(self, db: Session):
        reply = self._make_reply(db, email="invalid_sent@ex.com")
        with pytest.raises(ValueError, match="invalide"):
            update_reply_sentiment(reply.id, "maybe", db)

    def test_raises_when_reply_not_found(self, db: Session):
        with pytest.raises(ValueError, match="introuvable"):
            update_reply_sentiment(99999, "positive", db)

    def test_all_valid_sentiments_accepted(self, db: Session):
        for i, sentiment in enumerate(("positive", "negative", "neutral", "auto", "unknown")):
            reply = self._make_reply(db, email=f"valid_sent_{i}@ex.com")
            result = update_reply_sentiment(reply.id, sentiment, db)
            assert result.sentiment == sentiment

    def test_updates_campaign_states_has_replied(self, db: Session):
        contact = _contact(db, email="upd_camp_replied@ex.com")
        state = CampaignState(contact_id=contact.id, campaign_name="camp")
        db.add(state)
        reply = Reply(
            contact_id=contact.id,
            from_email="them@ex.com",
            sentiment="neutral",
            received_at=datetime(2024, 6, 1),
        )
        db.add(reply)
        db.flush()

        result = update_reply_sentiment(reply.id, "negative", db)

        assert result.updated_campaign_states == 1
        assert state.has_replied is True
        assert state.reply_sentiment == "negative"
