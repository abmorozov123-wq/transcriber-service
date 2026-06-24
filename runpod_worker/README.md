# RunPod Worker

This image is intended for RunPod Serverless.

Use the commit-specific Docker tag for RunPod releases.

The worker runs a startup preflight for Hugging Face gated pyannote access.

Required endpoint environment variables:

```env
HF_TOKEN=...
HF_HOME=/runpod-volume/hf-cache
TRANSFORMERS_CACHE=/runpod-volume/hf-cache
WHISPERX_CACHE=/runpod-volume/whisperx-cache
```

Optional:

```env
RUNPOD_WORKER_DUMMY=false
BATCH_SIZE=16
```

Input:

```json
{
  "job_id": "job_...",
  "audio_url": "http://89.125.123.119/hear/jobs/job_.../download-audio?token=...",
  "language": "ru",
  "model": "medium",
  "diarization": true
}
```

Output:

```json
{
  "job_id": "job_...",
  "segments": [
    {
      "start": 0.0,
      "end": 3.2,
      "speaker": "SPEAKER_00",
      "text": "..."
    }
  ]
}
```
