import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import Settings


def create_job_id() -> str:
    return f"job_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(3)}"


def job_dir(settings: Settings, job_id: str) -> Path:
    path = settings.data_dir / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_suffix(filename: str | None) -> str:
    if not filename:
        return ".bin"
    suffix = Path(filename).suffix.lower()
    return suffix if suffix and len(suffix) <= 10 else ".bin"


async def save_upload_file(file: UploadFile, destination: Path, max_bytes: int) -> int:
    total = 0
    with destination.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Uploaded file is too large",
                )
            out.write(chunk)
    return total


def make_download_token(settings: Settings, job_id: str, expires_in_minutes: int = 60) -> str:
    expires = int((datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)).timestamp())
    payload = f"{job_id}:{expires}"
    signature = hmac.new(
        settings.download_token_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{expires}.{signature}"


def verify_download_token(settings: Settings, job_id: str, token: str) -> None:
    try:
        expires_text, signature = token.split(".", 1)
        expires = int(expires_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token") from exc

    if expires < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Expired token")

    payload = f"{job_id}:{expires}"
    expected = hmac.new(
        settings.download_token_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
