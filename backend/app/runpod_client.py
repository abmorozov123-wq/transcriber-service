import secrets
from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass(frozen=True)
class RunPodSubmitResult:
    runpod_job_id: str
    status: str


@dataclass(frozen=True)
class RunPodStatusResult:
    status: str
    output: dict | None = None
    error: str | None = None


class RunPodClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def submit_job(
        self,
        *,
        job_id: str,
        audio_url: str,
        language: str = "ru",
        model: str = "medium",
        diarization: bool = True,
        participants: list[str] | None = None,
    ) -> RunPodSubmitResult:
        if self.settings.runpod_dummy_mode:
            return RunPodSubmitResult(
                runpod_job_id=f"dummy_{job_id}_{secrets.token_hex(3)}",
                status="sent_to_runpod",
            )

        if not self.settings.runpod_api_key or not self.settings.runpod_endpoint_id:
            raise RuntimeError("RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID are required")

        url = f"https://api.runpod.ai/v2/{self.settings.runpod_endpoint_id}/run"
        payload = {
            "input": {
                "job_id": job_id,
                "audio_url": audio_url,
                "language": language,
                "model": model,
                "diarization": diarization,
                "participants": participants or [],
            }
        }
        headers = {"Authorization": f"Bearer {self.settings.runpod_api_key}"}

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return RunPodSubmitResult(
            runpod_job_id=data.get("id") or data.get("job_id") or job_id,
            status="sent_to_runpod",
        )

    async def get_status(self, runpod_job_id: str) -> RunPodStatusResult:
        if self.settings.runpod_dummy_mode:
            return RunPodStatusResult(
                status="COMPLETED",
                output={
                    "segments": [
                        {
                            "start": 0.0,
                            "end": 3.2,
                            "speaker": "SPEAKER_00",
                            "text": "Dummy transcription result.",
                        }
                    ]
                },
            )

        if not self.settings.runpod_api_key or not self.settings.runpod_endpoint_id:
            raise RuntimeError("RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID are required")

        url = f"https://api.runpod.ai/v2/{self.settings.runpod_endpoint_id}/status/{runpod_job_id}"
        headers = {"Authorization": f"Bearer {self.settings.runpod_api_key}"}

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        return RunPodStatusResult(
            status=data.get("status", "UNKNOWN"),
            output=data.get("output"),
            error=data.get("error"),
        )
