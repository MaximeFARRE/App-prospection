from datetime import datetime

from pydantic import BaseModel


class CampaignStateBase(BaseModel):
    contact_id: int
    campaign_name: str


class CampaignStateRead(CampaignStateBase):
    id: int
    intro_sent: bool
    followup_1_sent: bool
    followup_2_sent: bool
    has_replied: bool
    reply_sentiment: str | None
    intro_sent_at: datetime | None
    followup_1_sent_at: datetime | None
    followup_2_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
