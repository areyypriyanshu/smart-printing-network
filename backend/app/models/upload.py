import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_uploads_size_bytes"),
        CheckConstraint("page_count > 0", name="ck_uploads_page_count"),
        Index("uploads_customer_idx", "customer_id", text("created_at DESC")),
        Index(
            "uploads_purge_idx",
            "delete_after",
            postgresql_where="file_deleted_at IS NULL AND delete_after IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    file_key: Mapped[str] = mapped_column(Text, unique=True)
    original_filename: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    page_count: Mapped[int] = mapped_column(Integer)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
