from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db, init_db
from app.models import Job, JobStatus
from app.notifier import send_message
from app.runpod_client import RunPodClient
from app.schemas import JobResponse, UploadResponse
from app.storage import (
    create_job_id,
    job_dir,
    make_download_token,
    safe_suffix,
    save_upload_file,
    verify_download_token,
)


app = FastAPI(title="Transcriber Service")


@app.on_event("startup")
def on_startup() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "jobs").mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    token: str = Form(...),
    telegram_user_id: str | None = Form(default=None),
    participants: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> UploadResponse:
    if token != settings.upload_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid upload token")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job_id = create_job_id()
    directory = job_dir(settings, job_id)
    original_path = directory / f"original{safe_suffix(file.filename)}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    await save_upload_file(file, original_path, max_bytes)

    job = Job(
        id=job_id,
        user_id=telegram_user_id,
        status=JobStatus.uploaded.value,
        original_filename=file.filename,
        original_path=str(original_path),
        participants=participants,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        send_message,
        settings,
        telegram_user_id,
        f"File accepted.\nJob: {job.id}\nStatus: {job.status}",
    )

    if settings.auto_submit_runpod:
        download_token = make_download_token(settings, job_id)
        audio_url = f"{settings.public_base_url}/jobs/{job_id}/download-audio?token={download_token}"
        runpod = RunPodClient(settings)
        try:
            result = await runpod.submit_job(
                job_id=job_id,
                audio_url=audio_url,
                participants=parse_participants(participants),
            )
            job.status = result.status
            job.runpod_job_id = result.runpod_job_id
            job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
        except Exception as exc:
            job.status = JobStatus.failed.value
            job.error = str(exc)
            job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to submit RunPod job") from exc

    return UploadResponse(job_id=job.id, status=job.status)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/download-audio")
def download_audio(
    job_id: str,
    token: str = Query(...),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> FileResponse:
    verify_download_token(settings, job_id, token)
    job = db.get(Job, job_id)
    if not job or not job.original_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")

    path = Path(job.original_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file is missing")
    return FileResponse(path, filename=job.original_filename or path.name)


@app.get("/jobs/{job_id}/result.md")
def download_result_md(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return result_file_response(db, job_id, "result_md_path", "transcript.md")


@app.get("/jobs/{job_id}/result.txt")
def download_result_txt(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return result_file_response(db, job_id, "result_txt_path", "transcript.txt")


@app.post("/runpod/webhook")
async def runpod_webhook() -> dict[str, str]:
    return {"status": "accepted"}


def result_file_response(db: Session, job_id: str, attr: str, filename: str) -> FileResponse:
    job = db.get(Job, job_id)
    path_text = getattr(job, attr, None) if job else None
    if not path_text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    path = Path(path_text)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result file is missing")
    return FileResponse(path, filename=filename)


def parse_participants(participants: str | None) -> list[str]:
    if not participants:
        return []
    return [item.strip() for item in participants.replace("\n", ",").split(",") if item.strip()]
