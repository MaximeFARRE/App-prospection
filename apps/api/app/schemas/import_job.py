from datetime import datetime

from pydantic import BaseModel


class ImportJobRead(BaseModel):
    id: int
    filename: str
    total_rows: int
    created_count: int
    duplicate_count: int
    error_count: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
