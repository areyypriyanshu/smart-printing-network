import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class QualityPageResponse(BaseModel):
    """What was measured on one page."""

    page_number: int
    #: The lowest effective resolution of the pictures on the page. Null
    #: when the page has no picture on it.
    min_effective_dpi: float | None
    #: How sharp the pictures on the page are. Null when there are none.
    blur_score: float | None
    #: Zero or more of LOW_RESOLUTION, VERY_LOW_RESOLUTION, BLURRY.
    flags: list[str]


class QualityReportResponse(BaseModel):
    """The advisory report for one upload."""

    id: uuid.UUID
    upload_id: uuid.UUID
    #: PENDING, RUNNING, DONE or FAILED.
    status: str
    pages: list[QualityPageResponse]
    summary: dict[str, Any]
    error: str | None
    acknowledged: bool
    algorithm_version: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
