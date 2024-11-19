import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def create_uuid() -> str:
    return str(uuid.uuid4())


def now_utc():
    return datetime.utcnow()


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(primary_key=True, default=create_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    is_deleted: Mapped[bool] = mapped_column(default=False)
