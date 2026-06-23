from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class JobStatus(str, Enum):
    uploaded = "uploaded"
    queued = "queued"
    sent_to_runpod = "sent_to_runpod"
    runpod_processing = "runpod_processing"
    runpod_done = "runpod_done"
    postprocessing = "postprocessing"
    done = "done"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_md_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_txt_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    runpod_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    participants: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
