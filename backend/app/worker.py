import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import Job, JobStatus
from app.notifier import send_job_files, send_message
from app.postprocess import write_dummy_transcripts
from app.runpod_client import RunPodClient
from app.storage import job_dir, make_download_token


logger = logging.getLogger(__name__)


async def process_once() -> None:
    settings = get_settings()
    await submit_uploaded_jobs(settings)
    await poll_runpod_jobs(settings)


async def submit_uploaded_jobs(settings) -> None:
    if not settings.auto_submit_runpod:
        return

    with SessionLocal() as db:
        jobs = db.scalars(
            select(Job)
            .where(Job.status == JobStatus.uploaded.value)
            .order_by(Job.created_at.asc())
            .limit(5)
        ).all()

        for job in jobs:
            try:
                token = make_download_token(settings, job.id)
                audio_url = f"{settings.public_base_url}/jobs/{job.id}/download-audio?token={token}"
                result = await RunPodClient(settings).submit_job(
                    job_id=job.id,
                    audio_url=audio_url,
                    participants=parse_participants(job.participants),
                )
                job.status = result.status
                job.runpod_job_id = result.runpod_job_id
                job.updated_at = utcnow()
                await send_message(
                    settings,
                    job.user_id,
                    f"Job sent to RunPod.\nJob: {job.id}\nStatus: {job.status}",
                )
            except Exception as exc:
                logger.exception("Failed to submit job %s", job.id)
                job.status = JobStatus.failed.value
                job.error = str(exc)
                job.updated_at = utcnow()
        db.commit()


async def poll_runpod_jobs(settings) -> None:
    with SessionLocal() as db:
        jobs = db.scalars(
            select(Job)
            .where(Job.status.in_([JobStatus.sent_to_runpod.value, JobStatus.runpod_processing.value]))
            .order_by(Job.updated_at.asc())
            .limit(10)
        ).all()

        for job in jobs:
            if not job.runpod_job_id:
                continue

            try:
                status = await RunPodClient(settings).get_status(job.runpod_job_id)
                if status.status in {"IN_QUEUE", "IN_PROGRESS"}:
                    job.status = JobStatus.runpod_processing.value
                    job.updated_at = utcnow()
                    continue

                if status.status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                    job.status = JobStatus.failed.value
                    job.error = status.error or status.status
                    job.updated_at = utcnow()
                    await send_message(settings, job.user_id, f"Job failed.\nJob: {job.id}\nError: {job.error}")
                    continue

                if status.status == "COMPLETED":
                    complete_job(settings, job, status.output or {})
                    await send_job_files(settings, job)
            except Exception as exc:
                logger.exception("Failed to poll job %s", job.id)
                job.error = str(exc)
                job.updated_at = utcnow()
        db.commit()


def complete_job(settings, job: Job, output: dict) -> None:
    directory = job_dir(settings, job.id)
    raw_path = directory / "transcript_raw.json"
    raw_payload = {"job_id": job.id, **output}
    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    job.status = JobStatus.postprocessing.value
    job.raw_json_path = str(raw_path)
    job.updated_at = utcnow()

    md_path, txt_path = write_dummy_transcripts(directory, job.id)
    job.result_md_path = str(md_path)
    job.result_txt_path = str(txt_path)
    job.status = JobStatus.done.value
    job.completed_at = utcnow()
    job.updated_at = job.completed_at


def parse_participants(participants: str | None) -> list[str]:
    if not participants:
        return []
    return [item.strip() for item in participants.replace("\n", ",").split(",") if item.strip()]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    while True:
        await process_once()
        await asyncio.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
