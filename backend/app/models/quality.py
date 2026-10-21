import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class QualityReport(Base):
    """The advisory quality report for one upload.

    The report is kept even after the file itself has been deleted, so
    the record of what the customer was told survives. It says nothing
    about the price, and nothing in the order flow reads it.
    """

    __tablename__ = "quality_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','DONE','FAILED')",
            name="ck_quality_reports_status",
        ),
        Index("quality_reports_status_idx", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("uploads.id"), unique=True)
    #: PENDING, RUNNING, DONE or FAILED. A FAILED report is advisory too:
    #: it means the check could not be done, not that the file is bad.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    #: The measurements and flags, one entry per page.
    pages: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    #: The counts a summary needs: how many pages, how many flagged.
    summary: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    #: Why the analysis failed, when it failed. Never the file itself.
    error: Mapped[str | None] = mapped_column(Text)
    #: Whether the customer has seen the warnings and gone ahead anyway.
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())
    #: Which version of the algorithm produced the numbers, so two
    #: reports are never compared without knowing they were made the
    #: same way.
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
