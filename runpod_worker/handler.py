import os
import subprocess
import tempfile
from pathlib import Path

import requests
import runpod


def handler(event):
    input_data = event.get("input", {})
    dummy_mode = os.getenv("RUNPOD_WORKER_DUMMY", "false").lower() == "true"
    if dummy_mode:
        return dummy_response(input_data)

    patch_torchaudio()
    import torch
    import whisperx

    patch_torch_serialization(torch)

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

            patch_huggingface_hub_auth_compat()
            DiarizationPipeline, assign_word_speakers = get_diarization_api(whisperx)
            patch_huggingface_hub_auth_compat()
            verify_pyannote_access(hf_token)
            diarize_model = DiarizationPipeline(use_auth_token=hf_token, device=device)
            diarize_segments = diarize_model(str(wav_path))
            result = assign_word_speakers(diarize_segments, result)

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


def get_diarization_api(whisperx_module):
    pipeline = getattr(whisperx_module, "DiarizationPipeline", None)
    assign_word_speakers = getattr(whisperx_module, "assign_word_speakers", None)

    if pipeline and assign_word_speakers:
        return pipeline, assign_word_speakers

    from whisperx.diarize import DiarizationPipeline, assign_word_speakers

    return DiarizationPipeline, assign_word_speakers


def patch_huggingface_hub_auth_compat() -> None:
    import inspect
    import sys

    import huggingface_hub

    original_download = huggingface_hub.hf_hub_download
    if "use_auth_token" in inspect.signature(original_download).parameters:
        return
    if getattr(original_download, "_transcriber_auth_compat", False):
        compat_download = original_download
        pipeline_module = sys.modules.get("pyannote.audio.core.pipeline")
        if pipeline_module is not None:
            pipeline_module.hf_hub_download = compat_download
        return

    def hf_hub_download_compat(*args, **kwargs):
        if "use_auth_token" in kwargs and "token" not in kwargs:
            kwargs["token"] = kwargs.pop("use_auth_token")
        else:
            kwargs.pop("use_auth_token", None)
        return original_download(*args, **kwargs)

    hf_hub_download_compat._transcriber_auth_compat = True
    huggingface_hub.hf_hub_download = hf_hub_download_compat

    pipeline_module = sys.modules.get("pyannote.audio.core.pipeline")
    if pipeline_module is not None:
        pipeline_module.hf_hub_download = hf_hub_download_compat


def verify_pyannote_access(hf_token: str) -> None:
    from huggingface_hub import hf_hub_download

    try:
        hf_hub_download(
            repo_id="pyannote/speaker-diarization-3.1",
            filename="config.yaml",
            token=hf_token,
        )
    except Exception as exc:
        raise RuntimeError(
            "HF_TOKEN cannot download pyannote/speaker-diarization-3.1 config.yaml. "
            "Check RunPod endpoint env HF_TOKEN and accept the pyannote gated model terms."
        ) from exc


def startup_preflight() -> None:
    if os.getenv("RUNPOD_WORKER_DUMMY", "false").lower() == "true":
        return

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError("Startup preflight failed: HF_TOKEN is not set in RunPod environment variables.")

    patch_huggingface_hub_auth_compat()
    verify_pyannote_access(hf_token)
    print("Startup preflight ok: HF_TOKEN can access pyannote/speaker-diarization-3.1")


def patch_torchaudio() -> None:
    from dataclasses import dataclass

    import torchaudio

    if hasattr(torchaudio, "AudioMetaData"):
        return

    try:
        from torchaudio._backend.common import AudioMetaData

        torchaudio.AudioMetaData = AudioMetaData
    except Exception:
        @dataclass
        class AudioMetaData:
            sample_rate: int
            num_frames: int
            num_channels: int
            bits_per_sample: int
            encoding: str

        torchaudio.AudioMetaData = AudioMetaData

    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["ffmpeg"]


def patch_torch_serialization(torch_module) -> None:
    original_load = torch_module.load

    def trusted_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return original_load(*args, **kwargs)

    torch_module.load = trusted_load

    try:
        from omegaconf import DictConfig, ListConfig
        from omegaconf.base import ContainerMetadata

        torch_module.serialization.add_safe_globals([DictConfig, ListConfig, ContainerMetadata])
    except Exception:
        return


if __name__ == "__main__":
    startup_preflight()
    runpod.serverless.start({"handler": handler})
