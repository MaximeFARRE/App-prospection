"""Déduplication inter-fichiers (scan + fusion manuelle)."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sqlalchemy.orm import Session

from app.models.campaign_state import CampaignState
from app.models.company import Company
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
from app.services.dedupe_utils import merge_campaign_state, merge_contact_fields, norm, select_keeper


REVIEW_TAG = "[A_VERIFIER_DOUBLON_PROBABLE]"


@dataclass
class DuplicatePair:
    left_contact_id: int
    right_contact_id: int
    company_name: str | None
    left_first_name: str | None
    right_first_name: str | None
    last_name: str | None
    strategy: str
    suggested_keep_contact_id: int


@dataclass
class DuplicateScanResult:
    probable_pairs: list[DuplicatePair]
    possible_pairs: list[DuplicatePair]
    marked_contacts_count: int


@dataclass
class MergeResult:
    kept_contact_id: int
    removed_contact_id: int
    transferred_campaign_states: int
    transferred_messages: int
    transferred_replies: int


def scan_duplicates(db: Session, mark_probable: bool = True) -> DuplicateScanResult:
    """Stratégie 2/3: détecte doublons probables et possibles.

    Stratégie 1 (email_normalized identique) est déjà gérée à l'import CSV.
    """
    rows = db.query(Contact, Company).outerjoin(Company, Company.id == Contact.company_id).all()
    probable_pairs = _find_probable_pairs(rows)
    probable_contact_ids = {p.left_contact_id for p in probable_pairs} | {p.right_contact_id for p in probable_pairs}
    possible_pairs = _find_possible_pairs(rows, excluded_contact_ids=probable_contact_ids)

    marked_contacts_count = 0
    if mark_probable and probable_contact_ids:
        marked_contacts_count = _mark_contacts_for_review(db, probable_contact_ids)
        db.flush()

    return DuplicateScanResult(
        probable_pairs=probable_pairs,
        possible_pairs=possible_pairs,
        marked_contacts_count=marked_contacts_count,
    )


def merge_contacts(db: Session, contact_a_id: int, contact_b_id: int) -> MergeResult:
    """Fusionne deux contacts: garde le plus complet, transfère les données, supprime l'autre."""
    if contact_a_id == contact_b_id:
        raise ValueError("Impossible de fusionner un contact avec lui-même.")

    left = db.query(Contact).filter(Contact.id == contact_a_id).first()
    right = db.query(Contact).filter(Contact.id == contact_b_id).first()
    if left is None or right is None:
        raise ValueError("Au moins un contact est introuvable.")

    keeper, removed = select_keeper(left, right)
    merge_contact_fields(keeper, removed)

    transferred_campaign_states = _transfer_campaign_states(db, keeper.id, removed.id)
    transferred_messages = _transfer_messages(db, keeper.id, removed.id)
    transferred_replies = _transfer_replies(db, keeper.id, removed.id)

    db.delete(removed)
    db.flush()

    return MergeResult(
        kept_contact_id=keeper.id,
        removed_contact_id=removed.id,
        transferred_campaign_states=transferred_campaign_states,
        transferred_messages=transferred_messages,
        transferred_replies=transferred_replies,
    )


def _find_probable_pairs(rows: list[tuple[Contact, Company | None]]) -> list[DuplicatePair]:
    buckets: dict[tuple[str, str, int], list[tuple[Contact, Company | None]]] = {}
    for contact, company in rows:
        first = norm(contact.first_name)
        last = norm(contact.last_name)
        if not first or not last or contact.company_id is None:
            continue
        buckets.setdefault((first, last, contact.company_id), []).append((contact, company))

    pairs: list[DuplicatePair] = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        for left, right in combinations(members, 2):
            left_contact, left_company = left
            right_contact, _ = right
            suggested_keep = select_keeper(left_contact, right_contact)[0]
            pairs.append(
                DuplicatePair(
                    left_contact_id=left_contact.id,
                    right_contact_id=right_contact.id,
                    company_name=left_company.name if left_company else None,
                    left_first_name=left_contact.first_name,
                    right_first_name=right_contact.first_name,
                    last_name=left_contact.last_name,
                    strategy="probable",
                    suggested_keep_contact_id=suggested_keep.id,
                )
            )
    return pairs


def _find_possible_pairs(
    rows: list[tuple[Contact, Company | None]],
    excluded_contact_ids: set[int],
) -> list[DuplicatePair]:
    buckets: dict[tuple[str, int], list[tuple[Contact, Company | None]]] = {}
    for contact, company in rows:
        if contact.id in excluded_contact_ids:
            continue
        last = norm(contact.last_name)
        if not last or contact.company_id is None:
            continue
        buckets.setdefault((last, contact.company_id), []).append((contact, company))

    pairs: list[DuplicatePair] = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        first_names = {norm(c.first_name) for c, _ in members if norm(c.first_name)}
        if len(first_names) < 2:
            continue

        for left, right in combinations(members, 2):
            left_contact, left_company = left
            right_contact, _ = right
            if norm(left_contact.first_name) == norm(right_contact.first_name):
                continue
            suggested_keep = select_keeper(left_contact, right_contact)[0]
            pairs.append(
                DuplicatePair(
                    left_contact_id=left_contact.id,
                    right_contact_id=right_contact.id,
                    company_name=left_company.name if left_company else None,
                    left_first_name=left_contact.first_name,
                    right_first_name=right_contact.first_name,
                    last_name=left_contact.last_name,
                    strategy="possible",
                    suggested_keep_contact_id=suggested_keep.id,
                )
            )
    return pairs


def _mark_contacts_for_review(db: Session, contact_ids: set[int]) -> int:
    contacts = db.query(Contact).filter(Contact.id.in_(contact_ids)).all()
    marked = 0
    for contact in contacts:
        notes = contact.notes or ""
        if REVIEW_TAG in notes:
            continue
        contact.notes = f"{notes}\n{REVIEW_TAG}".strip()
        marked += 1
    return marked


def _transfer_campaign_states(db: Session, keeper_id: int, removed_id: int) -> int:
    keep_states = db.query(CampaignState).filter(CampaignState.contact_id == keeper_id).all()
    keep_by_campaign = {state.campaign_name: state for state in keep_states}
    removed_states = db.query(CampaignState).filter(CampaignState.contact_id == removed_id).all()

    transferred = 0
    for removed_state in removed_states:
        existing = keep_by_campaign.get(removed_state.campaign_name)
        if existing is None:
            removed_state.contact_id = keeper_id
        else:
            merge_campaign_state(existing, removed_state)
            db.delete(removed_state)
        transferred += 1
    return transferred


def _transfer_messages(db: Session, keeper_id: int, removed_id: int) -> int:
    messages = db.query(Message).filter(Message.contact_id == removed_id).all()
    for message in messages:
        message.contact_id = keeper_id
    return len(messages)


def _transfer_replies(db: Session, keeper_id: int, removed_id: int) -> int:
    replies = db.query(Reply).filter(Reply.contact_id == removed_id).all()
    for reply in replies:
        reply.contact_id = keeper_id
    return len(replies)

