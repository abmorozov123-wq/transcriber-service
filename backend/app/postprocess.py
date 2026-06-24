import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings


SYSTEM_PROMPT = """Ты редактор расшифровок аудиозаписей. Твоя задача — превратить сырую ASR-расшифровку с таймкодами и speaker labels в чистый, удобный для чтения текст.

Общий контекст: этот разговор скорее всего переговоры в бизнесах альфа-групп. Важные аббревиатуры и бизнесы, которые надо учесть при исправлении спорных слов: CTF (ситиэф), Альфа-Банк, Альфа-Страхование, X5 (икс пять), А1 (а один), Боржоми, Альфакап (Альфа-Капитал), РВК (Росводоканал). Фамилии: Верхошинский, Гиязов, Афендиков, Корня, Эмдин, Шехтерман, Анохин.

Правила:
1. Не выдумывай факты, имена, должности, даты и контекст.
2. Сохраняй смысл сказанного максимально точно.
3. Убирай мусор распознавания: повторы, междометия, ложные старты, очевидные ASR-ошибки, если их можно исправить без изменения смысла.
4. Не удаляй важные оговорки, сомнения, договоренности, цифры, имена, сроки.
5. Сохраняй роли говорящих. Если имена участников неизвестны, используй SPEAKER_00, SPEAKER_01 и т.д.
6. Если имя или термин распознаны сомнительно, пометь знаком вопроса: Иван? или термин?.
7. Не объединяй реплики разных говорящих.
8. Если подряд идут реплики одного говорящего, можно объединить их в один абзац.
9. Сохраняй таймкоды в markdown-версии.
10. Верни результат строго в JSON с двумя полями: markdown и plain_text."""


def write_transcripts(
    job_dir: Path,
    job_id: str,
    raw_payload: dict[str, Any],
    participants: list[str],
    settings: Settings,
    accepted_at: datetime,
) -> tuple[Path, Path]:
    md_path = job_dir / "transcript_speakers.md"
    txt_path = job_dir / "transcript_clean.txt"

    try:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        result = call_deepseek(raw_payload, participants, settings)
        markdown = normalize_text(result["markdown"])
        plain_text = normalize_text(result["plain_text"])
    except Exception as exc:
        markdown, plain_text = fallback_transcripts(job_id, raw_payload, exc)

    plain_text = add_conversation_time_header(plain_text, raw_payload, accepted_at)
    md_path.write_text(markdown + "\n", encoding="utf-8")
    txt_path.write_text(plain_text + "\n", encoding="utf-8")
    return md_path, txt_path


def call_deepseek(
    raw_payload: dict[str, Any],
    participants: list[str],
    settings: Settings,
) -> dict[str, str]:
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(raw_payload, participants)},
        ],
        "temperature": 0.1,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"

    with httpx.Client(timeout=120) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    parsed = parse_json_object(content)
    markdown = parsed.get("markdown")
    plain_text = parsed.get("plain_text")
    if not isinstance(markdown, str) or not isinstance(plain_text, str):
        raise RuntimeError("LLM response must contain string fields: markdown, plain_text")
    return {"markdown": markdown, "plain_text": plain_text}


def build_user_prompt(raw_payload: dict[str, Any], participants: list[str]) -> str:
    participant_text = ", ".join(participants) if participants else "не указаны"
    raw_json = json.dumps(raw_payload, ensure_ascii=False, indent=2)
    return f"""Обработай эту расшифровку.

Участники, если известны:
{participant_text}

Сырая расшифровка в JSON:
{raw_json}

Нужно вернуть JSON:
{{
  "markdown": "...",
  "plain_text": "..."
}}

Требования к markdown:
- Заголовок: "# Расшифровка"
- Затем краткий блок "Участники", если можно определить роли.
- Затем основной текст по репликам.
- Формат реплики: "[00:01:23] SPEAKER_00: текст"
- Если понятна роль, можно писать: "[00:01:23] Клиент: текст"
- Не добавляй выводы, которых нет в записи.

Требования к plain_text:
- Без markdown-разметки.
- В начале укажи дату и время начала и конца разговора.
- Чистый читабельный текст.
- Сохраняй speaker labels или роли."""


def parse_json_object(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def fallback_transcripts(
    job_id: str,
    raw_payload: dict[str, Any],
    error: Exception,
) -> tuple[str, str]:
    lines = format_segment_lines(raw_payload)
    reason = f"{type(error).__name__}: {error}"
    markdown = "\n".join(
        [
            "# Расшифровка",
            "",
            f"Job: `{job_id}`",
            "",
            "> LLM post-processing failed. Ниже сохранена аккуратная fallback-расшифровка из raw JSON.",
            f"> Ошибка: `{reason}`",
            "",
            *lines,
        ]
    )
    plain_text = "\n".join(
        [
            "Расшифровка",
            "",
            f"Job: {job_id}",
            "",
            "LLM post-processing failed. Ниже fallback-расшифровка из raw JSON.",
            f"Ошибка: {reason}",
            "",
            *lines,
        ]
    )
    return markdown, plain_text


def format_segment_lines(raw_payload: dict[str, Any]) -> list[str]:
    lines = []
    for segment in raw_payload.get("segments", []):
        start = format_timestamp(float(segment.get("start", 0.0)))
        speaker = segment.get("speaker") or "SPEAKER_UNKNOWN"
        text = normalize_text(segment.get("text") or "")
        if text:
            lines.append(f"[{start}] {speaker}: {text}")
    return lines or ["[00:00:00] SPEAKER_UNKNOWN: Распознанный текст отсутствует."]


def add_conversation_time_header(
    plain_text: str,
    raw_payload: dict[str, Any],
    accepted_at: datetime,
) -> str:
    start_at, end_at = conversation_time_range(raw_payload, accepted_at)
    header = "\n".join(
        [
            f"Начало разговора: {format_local_datetime(start_at)}",
            f"Конец разговора: {format_local_datetime(end_at)}",
            "",
        ]
    )
    body = strip_existing_time_header(plain_text)
    return header + body


def conversation_time_range(
    raw_payload: dict[str, Any],
    accepted_at: datetime,
) -> tuple[datetime, datetime]:
    base = accepted_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    segments = raw_payload.get("segments", [])
    starts = [float(item.get("start", 0.0)) for item in segments]
    ends = [float(item.get("end", 0.0)) for item in segments]
    start_offset = min(starts) if starts else 0.0
    end_offset = max(ends) if ends else start_offset
    return base + timedelta(seconds=start_offset), base + timedelta(seconds=end_offset)


def format_local_datetime(value: datetime) -> str:
    return value.astimezone(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S")


def strip_existing_time_header(value: str) -> str:
    lines = value.splitlines()
    while lines and (
        lines[0].startswith("Начало разговора:")
        or lines[0].startswith("Конец разговора:")
        or lines[0].startswith("Дата и время начала:")
        or lines[0].startswith("Дата и время окончания:")
        or lines[0].startswith("Время начала:")
        or lines[0].startswith("Время окончания:")
        or not lines[0].strip()
    ):
        lines.pop(0)
    return "\n".join(lines).strip()


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def normalize_text(value: str) -> str:
    return value.strip().replace("\r\n", "\n").replace("\r", "\n")
