from datetime import datetime

from pydantic import BaseModel


class ReplyRead(BaseModel):
    id: int
    contact_id: int
    in_reply_to_message_id: int | None
    subject: str | None
    body: str | None
    from_email: str
    gmail_thread_id: str | None
    sentiment: str | None
    received_at: datetime

    model_config = {"from_attributes": True}


class ReplyUpdateSentiment(BaseModel):
    """Payload pour corriger manuellement la classification d'une réponse."""
    sentiment: str
