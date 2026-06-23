from datetime import datetime

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    status: str
    user_id: str | None
    original_filename: str | None
    runpod_job_id: str | None
    error: str | None
    participants: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    job_id: str
    status: str
