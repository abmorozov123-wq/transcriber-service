import os
import subprocess
import tempfile
from pathlib import Path

import requests
import runpod
import torch
import whisperx


def handler(event):
    input_data = event.get("input", {})
    dummy_mode = os.getenv("RUNPOD_WORKER_DUMMY", "false").lower() == "true"
    if dummy_mode:
        return dummy_response(input_data)

    job_id = input_data["job_id"]
    audio_url = input_data["audio_url"]
    language = input_data.get("language", "ru")
    model_name = input_data.get("model", "medium")
    diarization_enabled = bool(input_data.get("diarization", True))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        source_path = tmp_dir / "original_audio"
        wav_path = tmp_dir / "audio.wav"

        download_file(audio_url, source_path)
        convert_to_wav(source_path, wav_path)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        model = whisperx.load_model(
            model_name,
            device,
            language=language,
            compute_type=compute_type,
            download_root=os.getenv("WHISPERX_CACHE", "/runpod-volume/whisperx-cache"),
        )
        result = model.transcribe(str(wav_path), batch_size=int(os.getenv("BATCH_SIZE", "16")))

        align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
        result = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            str(wav_path),
            device,
            return_char_alignments=False,
        )

        if diarization_enabled:
            hf_token = os.getenv("HF_TOKEN")
            if not hf_token:
                raise RuntimeError("HF_TOKEN is required for pyannote diarization")

            diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
            diarize_segments = diarize_model(str(wav_path))
            result = whisperx.assign_word_speakers(diarize_segments, result)

        return {
            "job_id": job_id,
            "language": language,
            "model": model_name,
            "segments": normalize_segments(result.get("segments", [])),
        }


def download_file(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with destination.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    out.write(chunk)


def convert_to_wav(source: Path, destination: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(destination),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def normalize_segments(segments):
    normalized = []
    for item in segments:
        normalized.append(
            {
                "start": float(item.get("start", 0.0)),
                "end": float(item.get("end", 0.0)),
                "speaker": item.get("speaker") or "SPEAKER_UNKNOWN",
                "text": (item.get("text") or "").strip(),
            }
        )
    return normalized


def dummy_response(input_data):
    return {
        "job_id": input_data.get("job_id"),
        "segments": [
            {
                "start": 0.0,
                "end": 3.2,
                "speaker": "SPEAKER_00",
                "text": "Dummy RunPod worker response.",
            }
        ],
    }


runpod.serverless.start({"handler": handler})
