from datetime import datetime

from pydantic import BaseModel


class CompanyRead(BaseModel):
    id: int
    name: str
    website: str | None
    linkedin_url: str | None
    country: str | None
    source_business_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyCreate(BaseModel):
    name: str
    website: str | None = None
    linkedin_url: str | None = None
    country: str | None = None
    source_business_id: str | None = None
