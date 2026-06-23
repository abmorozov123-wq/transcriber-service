# Transcriber Service MVP

Personal service for uploading long iPhone voice memos, queueing transcription jobs, sending GPU work to RunPod, and delivering results through Telegram.

## What is implemented now

- `GET /health`
- `POST /upload`
- SQLite `jobs` table
- Local file storage under `data/jobs/{job_id}`
- Protected temporary audio download URL for RunPod
- Telegram bot commands: `/start`, `/help`, `/status job_id`
- Dummy RunPod client mode
- Minimal dummy RunPod worker image

## Local run

```bash
cp .env.example .env
docker compose up --build backend
```

Health check:

```bash
curl http://localhost:8000/health
```

Upload test:

```bash
curl -F "token=replace-with-random-token" \
  -F "telegram_user_id=123456" \
  -F "participants=Anton, Mikhail" \
  -F "file=@sample.m4a" \
  http://localhost:8000/upload
```

Check status:

```bash
curl http://localhost:8000/jobs/{job_id}
```

Run bot after setting `TELEGRAM_BOT_TOKEN`:

```bash
docker compose --profile bot up --build telegram-bot
```

Run the background worker:

```bash
python -m app.worker
```

## Deploy under `/hear`

If the IP already hosts another service, expose this app under:

```text
http://89.125.123.119/hear
```

Use this value in `.env`:

```env
PUBLIC_BASE_URL=http://89.125.123.119/hear
```

Nginx can strip the `/hear` prefix before proxying to FastAPI:

```nginx
location /hear/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 1024m;
}
```

Then health check is:

```bash
curl http://89.125.123.119/hear/health
```

## Next steps

1. Add RunPod polling and saving `transcript_raw.json`.
2. Build and deploy the dummy RunPod worker image.
3. Replace dummy worker with WhisperX and pyannote.
4. Add DeepSeek post-processing and Telegram result delivery.
5. Prepare iOS Shortcut instructions.

## Required secrets

Keep secrets only in `.env`:

- `UPLOAD_TOKEN`
- `DOWNLOAD_TOKEN_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `RUNPOD_API_KEY`
- `RUNPOD_ENDPOINT_ID`
- `HF_TOKEN`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
