from datetime import datetime

from pydantic import BaseModel


class MessageRead(BaseModel):
    id: int
    contact_id: int
    campaign_name: str | None
    subject: str
    body: str
    from_email: str
    message_type: str
    gmail_message_id: str | None
    sent_at: datetime

    model_config = {"from_attributes": True}
