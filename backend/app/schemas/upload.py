import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    size_bytes: int
    page_count: int
    created_at: datetime
