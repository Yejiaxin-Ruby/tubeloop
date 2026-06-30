from __future__ import annotations

import html
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "youtube-english-web"
DB_PATH = Path(
    os.getenv("APP_DB_PATH", str(Path(__file__).with_name("youtube_learning.sqlite3"))),
).expanduser()
APP_PORT = int(os.getenv("PORT", "8000"))
MOCK_URL = "https://www.youtube.com/watch?v=mock-english-thinking"
AI_BUILDER_BASE_URL = "https://space.ai-builders.com/backend/v1"
AI_BUILDER_CHAT_MODEL = "gpt-5"
AI_BUILDER_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
SUPADATA_BASE_URL = "https://api.supadata.ai/v1"
MAX_VIDEO_SECONDS = 60 * 60
CAPTION_BREAK_PATTERN = re.compile(r"[,.!?;:，。！？；：]$")
MAX_MERGED_CAPTION_CHARS = 140
MAX_MERGED_CAPTION_SECONDS = 14

load_dotenv(ROOT_DIR / ".env")

app = FastAPI(title="Tubeloop")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImportVideoRequest(BaseModel):
    url: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    video_id: int
    message: str = Field(..., min_length=1)


class ExpressionCardRequest(BaseModel):
    video_id: int
    source_type: str = "subtitle"
    expression_text: str = Field(..., min_length=1)
    chinese_meaning: str = ""
    context: str = ""
    timestamp: str = ""
    note: str = ""


class TranslationRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ExpressionExplainRequest(BaseModel):
    expression_text: str = Field(..., min_length=1)
    context: str = ""


class ImportedSubtitle(BaseModel):
    start_seconds: float
    end_seconds: float
    en: str
    zh: str = ""


class ImportedVideo(BaseModel):
    youtube_url: str
    youtube_video_id: str
    title: str
    channel: str
    duration: str
    thumbnail_url: str = ""
    summary: str = ""
    subtitles: list[ImportedSubtitle]


MOCK_VIDEO: dict[str, Any] = {
    "youtube_url": MOCK_URL,
    "title": "How to Think in English",
    "channel": "English Learning Podcast",
    "duration": "18:42",
    "thumbnail_tone": "blue",
    "summary": (
        "This video explains how English learners can start thinking directly "
        "in English by connecting language with meaningful input, images, "
        "actions, and personal experience."
    ),
}

MOCK_SUBTITLES: list[dict[str, str]] = [
    {
        "time": "00:18",
        "start_time": "00:18",
        "end_time": "00:23",
        "en": "The real shift happens when you stop translating every sentence in your head.",
        "zh": "真正的转变发生在你不再在脑子里逐句翻译的时候。",
    },
    {
        "time": "00:24",
        "start_time": "00:24",
        "end_time": "00:32",
        "en": "Instead, you begin to connect English directly with images, actions, and feelings.",
        "zh": "相反，你会开始把英语直接和画面、动作、感受连接起来。",
    },
    {
        "time": "00:33",
        "start_time": "00:33",
        "end_time": "00:43",
        "en": "That is why repetition with meaningful content matters much more than isolated vocabulary.",
        "zh": "这就是为什么有意义内容里的重复，比孤立背单词更重要。",
    },
    {
        "time": "00:44",
        "start_time": "00:44",
        "end_time": "00:51",
        "en": "When you listen to something you actually care about, attention becomes easier.",
        "zh": "当你听的是自己真正关心的内容时，注意力会变得更容易维持。",
    },
    {
        "time": "00:52",
        "start_time": "00:52",
        "end_time": "01:02",
        "en": "And once you discuss the idea, the language becomes part of your own thinking.",
        "zh": "一旦你开始讨论这个观点，语言就会变成你自己思考的一部分。",
    },
    {
        "time": "01:03",
        "start_time": "01:03",
        "end_time": "01:12",
        "en": "The goal is not to memorize every word, but to build a personal library of useful expressions.",
        "zh": "目标不是记住每个词，而是建立一个属于自己的有用表达库。",
    },
]

SEED_CARDS: list[dict[str, str]] = [
    {
        "source_type": "subtitle",
        "expression_text": "stop translating every sentence",
        "chinese_meaning": "停止逐句翻译",
        "context": MOCK_SUBTITLES[0]["en"],
        "timestamp": "00:18",
        "note": "",
    },
    {
        "source_type": "subtitle",
        "expression_text": "meaningful content",
        "chinese_meaning": "有意义的内容",
        "context": MOCK_SUBTITLES[2]["en"],
        "timestamp": "00:33",
        "note": "",
    },
    {
        "source_type": "conversation",
        "expression_text": "becomes part of your own thinking",
        "chinese_meaning": "变成你自己思考的一部分",
        "context": MOCK_SUBTITLES[4]["en"],
        "timestamp": "00:52",
        "note": "",
    },
]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def get_ai_builder_token() -> str | None:
    return os.getenv("AI_BUILDER_TOKEN")


def has_ai_builder_token() -> bool:
    return bool(get_ai_builder_token())


def get_supadata_key() -> str | None:
    return os.getenv("SUPADATA_API_KEY")


def call_builder_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int = 500,
) -> str:
    token = get_ai_builder_token()
    if not token:
        raise RuntimeError("AI_BUILDER_TOKEN is not configured")

    payload = {
        "model": os.getenv("AI_BUILDER_CHAT_MODEL", AI_BUILDER_CHAT_MODEL),
        "messages": messages,
        "max_tokens": max(max_tokens, 1000),
    }
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=45) as client:
        response = client.post(
            f"{AI_BUILDER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"].get("content") or ""
    content = content.strip()
    if not content:
        raise RuntimeError("AI Builder returned an empty response")
    return content


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def parse_json_array(text: str) -> list[Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("Expected JSON array")
    return data


def extract_youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
        return video_id or None
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        match = re.match(r"^/(embed|shorts|live)/([^/?#]+)", parsed.path)
        if match:
            return match.group(2)
    return None


def normalized_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_duration_seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if not isinstance(value, str):
        return 0
    text = value.strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    if ":" in text:
        parts = [int(part) for part in text.split(":") if part.isdigit()]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
    if match:
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    return 0


def format_seconds(total_seconds: float) -> str:
    total = max(0, int(total_seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def clean_caption_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = text.replace("\xa0", " ")
    text = text.replace("♪", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_caption_noise(text: str) -> bool:
    normalized = clean_caption_text(text).lower()
    normalized = normalized.strip("[](){}-:：.。!！?？,， ")
    if not normalized:
        return True
    return normalized in {
        "music",
        "applause",
        "laughter",
        "laughs",
        "silence",
        "background music",
        "foreign",
    }


def join_caption_texts(parts: list[str]) -> str:
    text = clean_caption_text(" ".join(clean_caption_text(part) for part in parts if clean_caption_text(part)))
    text = re.sub(r"\s+([,.!?;:，。！？；：])", r"\1", text)
    text = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", text)
    return text


def should_break_caption_group(text: str) -> bool:
    return bool(CAPTION_BREAK_PATTERN.search(clean_caption_text(text)))


def merge_caption_fragments(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        text = join_caption_texts([str(line.get("text", "")) for line in pending])
        if text and not is_caption_noise(text):
            merged.append(
                {
                    "start_seconds": float(pending[0]["start_seconds"]),
                    "end_seconds": float(pending[-1]["end_seconds"]),
                    "text": text,
                },
            )
        pending = []

    for line in sorted(lines, key=lambda item: float(item.get("start_seconds", 0))):
        text = clean_caption_text(str(line.get("text", "")))
        if not text or is_caption_noise(text):
            continue
        pending.append({**line, "text": text})
        combined = join_caption_texts([str(item.get("text", "")) for item in pending])
        duration = float(pending[-1]["end_seconds"]) - float(pending[0]["start_seconds"])
        if (
            should_break_caption_group(text)
            or len(combined) >= MAX_MERGED_CAPTION_CHARS
            or duration >= MAX_MERGED_CAPTION_SECONDS
        ):
            flush()

    flush()
    return merged


def parse_vtt_timestamp(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except ValueError:
        return 0.0
    return 0.0


def parse_json3_captions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        segs = event.get("segs") or []
        text = clean_caption_text("".join(str(seg.get("utf8", "")) for seg in segs))
        if not text or is_caption_noise(text):
            continue
        start = float(event.get("tStartMs") or 0) / 1000
        duration = float(event.get("dDurationMs") or 0) / 1000
        end = start + max(duration, 1.0)
        captions.append({"start_seconds": start, "end_seconds": end, "text": text})
    return captions


def parse_vtt_captions(text: str) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    pending_time: tuple[float, float] | None = None
    pending_text: list[str] = []

    def flush() -> None:
        nonlocal pending_time, pending_text
        if pending_time and pending_text:
            caption_text = clean_caption_text(" ".join(pending_text))
            if caption_text and not is_caption_noise(caption_text):
                captions.append(
                    {
                        "start_seconds": pending_time[0],
                        "end_seconds": pending_time[1],
                        "text": caption_text,
                    },
                )
        pending_time = None
        pending_text = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            flush()
            left, right = line.split("-->", 1)
            pending_time = (
                parse_vtt_timestamp(left),
                parse_vtt_timestamp(right.split()[0]),
            )
            continue
        if pending_time and not line.isdigit():
            pending_text.append(line)
    flush()
    return captions


def choose_caption_track(
    tracks: dict[str, list[dict[str, Any]]],
    preferred_prefixes: tuple[str, ...],
) -> list[dict[str, Any]] | None:
    if not tracks:
        return None
    candidates: list[tuple[int, str, list[dict[str, Any]]]] = []
    for language, entries in tracks.items():
        normalized = language.lower()
        for rank, prefix in enumerate(preferred_prefixes):
            if normalized == prefix or normalized.startswith(f"{prefix}-"):
                candidates.append((rank, language, entries))
                break
    if not candidates:
        return None
    _, _, entries = sorted(candidates, key=lambda item: item[0])[0]
    return sorted(
        entries,
        key=lambda entry: 0
        if entry.get("ext") == "json3"
        else 1
        if entry.get("ext") in {"vtt", "srv3", "srv2"}
        else 2,
    )


def fetch_caption_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for entry in entries:
            caption_url = entry.get("url")
            if not caption_url:
                continue
            try:
                response = client.get(caption_url)
                response.raise_for_status()
                ext = entry.get("ext")
                content_type = response.headers.get("content-type", "")
                if ext == "json3" or "json" in content_type:
                    return parse_json3_captions(response.json())
                return parse_vtt_captions(response.text)
            except Exception as error:
                last_error = error
    if last_error:
        raise last_error
    return []


def supadata_segments_to_caption_lines(segments: list[Any]) -> list[dict[str, Any]]:
    if not segments:
        return []

    sample_values: list[float] = []
    for item in segments[:5]:
        if not isinstance(item, dict):
            continue
        raw_start = item.get("offset", item.get("start", 0))
        try:
            value = float(raw_start or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            sample_values.append(value)
    is_milliseconds = bool(sample_values) and (sum(sample_values) / len(sample_values)) > 500

    lines: list[dict[str, Any]] = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        text = clean_caption_text(str(item.get("text") or item.get("content") or ""))
        if not text or is_caption_noise(text):
            continue
        try:
            raw_start = float(item.get("offset", item.get("start", 0)) or 0)
            raw_duration = float(item.get("duration", 0) or 0)
        except (TypeError, ValueError):
            continue
        start = raw_start / 1000 if is_milliseconds else raw_start
        duration = raw_duration / 1000 if is_milliseconds else raw_duration
        lines.append(
            {
                "start_seconds": start,
                "end_seconds": start + max(duration, 0.5),
                "text": text,
            },
        )
    return lines


def supadata_response_segments(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("content", "transcript", "segments"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def fetch_supadata_transcript_lines(
    video_id: str,
    lang: str | None = "en",
) -> list[dict[str, Any]]:
    api_key = get_supadata_key()
    if not api_key:
        return []

    params = {"url": normalized_youtube_url(video_id)}
    if lang:
        params["lang"] = lang
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        response = client.get(
            f"{SUPADATA_BASE_URL}/transcript",
            params=params,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
        )

    if response.status_code == 404:
        return []
    if not response.is_success or response.status_code == 206:
        raise RuntimeError(f"Supadata transcript failed: {response.status_code} {response.text[:200]}")

    segments = supadata_response_segments(response.json())
    return supadata_segments_to_caption_lines(segments)


def fetch_supadata_english_lines(video_id: str) -> list[dict[str, Any]]:
    if not get_supadata_key():
        return []
    for lang in ("en", None):
        lines = fetch_supadata_transcript_lines(video_id, lang)
        if lines:
            return lines
    return []


def fetch_supadata_video_info(video_id: str) -> dict[str, Any]:
    api_key = get_supadata_key()
    if not api_key:
        return {}
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(
                f"{SUPADATA_BASE_URL}/youtube/video",
                params={"id": video_id},
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
            )
        if not response.is_success:
            print(f"[supadata video info failed] HTTP {response.status_code}: {response.text[:200]}", flush=True)
            return {}
        data = response.json()
        return {
            "title": data.get("title") or "YouTube Video",
            "channel": (data.get("channel") or {}).get("name") if isinstance(data.get("channel"), dict) else data.get("author"),
            "duration_seconds": parse_duration_seconds(data.get("duration")),
            "thumbnail": data.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "description": data.get("description") or "",
        }
    except Exception as error:
        print(f"[supadata video info failed] {type(error).__name__}: {error}", flush=True)
        return {}


def fetch_oembed_video_info(video_id: str) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(
                "https://www.youtube.com/oembed",
                params={"url": normalized_youtube_url(video_id), "format": "json"},
            )
        if not response.is_success:
            return {}
        data = response.json()
        return {
            "title": data.get("title") or "YouTube Video",
            "channel": data.get("author_name") or "Unknown",
            "duration_seconds": 0,
            "thumbnail": data.get("thumbnail_url") or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "description": "",
        }
    except Exception as error:
        print(f"[youtube oembed failed] {type(error).__name__}: {error}", flush=True)
        return {}


def default_video_info(video_id: str) -> dict[str, Any]:
    return {
        "title": "YouTube Video",
        "channel": "Unknown",
        "duration_seconds": 0,
        "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        "description": "",
    }


def merge_video_info(base: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in fallback.items():
        if key == "duration_seconds":
            if not int(merged.get(key) or 0) and int(value or 0):
                merged[key] = int(value)
        elif not merged.get(key) and value:
            merged[key] = value
    return merged


def fetch_video_info_with_fallback(video_id: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    info = merge_video_info(info, fetch_oembed_video_info(video_id))
    info = merge_video_info(info, default_video_info(video_id))
    return info


def match_translation_line(
    line: dict[str, Any],
    translated_lines: list[dict[str, Any]],
) -> str:
    best_text = ""
    best_score = -9999.0
    start = float(line["start_seconds"])
    end = float(line["end_seconds"])
    for translated in translated_lines:
        other_start = float(translated["start_seconds"])
        other_end = float(translated["end_seconds"])
        overlap = max(0.0, min(end, other_end) - max(start, other_start))
        distance = abs(start - other_start)
        score = overlap * 10 - distance
        if score > best_score:
            best_score = score
            best_text = str(translated["text"])
    return best_text if best_score > -6 else ""


def match_translation_range(
    line: dict[str, Any],
    translated_lines: list[dict[str, Any]],
) -> str:
    start = float(line["start_seconds"])
    end = float(line["end_seconds"])
    matched: list[dict[str, Any]] = []
    for translated in translated_lines:
        other_start = float(translated["start_seconds"])
        other_end = float(translated["end_seconds"])
        midpoint = (other_start + other_end) / 2
        overlap = max(0.0, min(end, other_end) - max(start, other_start))
        if overlap > 0.05 or start <= midpoint <= end:
            matched.append(translated)
    if matched:
        return join_caption_texts([str(item.get("text", "")) for item in matched])
    return match_translation_line(line, translated_lines)


def transcript_snippet_value(snippet: Any, key: str, default: Any = None) -> Any:
    if isinstance(snippet, dict):
        return snippet.get(key, default)
    return getattr(snippet, key, default)


def transcript_to_caption_lines(fetched: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for snippet in fetched:
        text = clean_caption_text(str(transcript_snippet_value(snippet, "text", "")))
        if not text or is_caption_noise(text):
            continue
        start = float(transcript_snippet_value(snippet, "start", 0) or 0)
        duration = float(transcript_snippet_value(snippet, "duration", 0) or 0)
        lines.append(
            {
                "start_seconds": start,
                "end_seconds": start + max(duration, 0.5),
                "text": text,
            },
        )
    return lines


def fetch_transcript_caption_lines(
    video_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    english_transcript = transcript_list.find_transcript(["en"])
    english_lines = transcript_to_caption_lines(english_transcript.fetch())

    chinese_lines: list[dict[str, Any]] = []
    try:
        chinese_transcript = transcript_list.find_transcript(["zh-CN", "zh-Hans", "zh"])
        chinese_lines = transcript_to_caption_lines(chinese_transcript.fetch())
    except Exception:
        if english_transcript.is_translatable:
            try:
                translated = english_transcript.translate("zh-Hans")
                chinese_lines = transcript_to_caption_lines(translated.fetch())
            except Exception as error:
                print(f"[transcript translation fallback] {type(error).__name__}: {error}", flush=True)
    return english_lines, chinese_lines


def translate_caption_lines(lines: list[dict[str, Any]]) -> list[str]:
    if not lines:
        return []
    chunk_size = 2
    translations: list[str] = []
    for chunk_start in range(0, len(lines), chunk_size):
        chunk = lines[chunk_start : chunk_start + chunk_size]
        translations.extend(translate_caption_chunk(chunk))
    return translations


def translate_caption_chunk(lines: list[dict[str, Any]]) -> list[str]:
    if not lines:
        return []
    if len(lines) == 1:
        try:
            return [
                call_builder_chat(
                    [
                        {
                            "role": "system",
                            "content": "Translate this English subtitle into concise natural Simplified Chinese. Return only the translation.",
                        },
                        {"role": "user", "content": str(lines[0]["text"])},
                    ],
                    max_tokens=220,
                ).strip(),
            ]
        except Exception as error:
            print(f"[single subtitle translation failed] {type(error).__name__}: {error}", flush=True)
            return [""]

    numbered = "\n".join(
        f"{index + 1}. {line['text']}"
        for index, line in enumerate(lines)
    )
    try:
        raw = call_builder_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Translate English subtitle lines into concise, natural Simplified Chinese. "
                        "Return a strict JSON array only. Keep the same order and same item count."
                    ),
                },
                {"role": "user", "content": numbered},
            ],
            max_tokens=max(700, len(lines) * 120),
        )
        parsed = [str(item).strip() for item in parse_json_array(raw)]
        if len(parsed) != len(lines):
            raise ValueError("Translation count mismatch")
        return parsed
    except Exception as error:
        print(f"[subtitle translation split retry] {type(error).__name__}: {error}", flush=True)
        midpoint = len(lines) // 2
        return translate_caption_chunk(lines[:midpoint]) + translate_caption_chunk(lines[midpoint:])


def subtitle_translation_counts(db: sqlite3.Connection, video_id: int) -> dict[str, int]:
    row = db.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN TRIM(chinese_text) != '' THEN 1 ELSE 0 END) AS translated
        FROM subtitle_lines
        WHERE video_id = ?
        """,
        (video_id,),
    ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "translated": int(row["translated"] or 0),
    }


def update_chinese_translation_status(
    db: sqlite3.Connection,
    video_id: int,
    status: str,
    error: str = "",
) -> None:
    db.execute(
        """
        UPDATE videos
        SET chinese_translation_status = ?,
            chinese_translation_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, error, video_id),
    )


def generate_chinese_subtitles_task(video_id: int) -> None:
    with connect() as db:
        rows = [
            row_to_dict(row)
            for row in db.execute(
                """
                SELECT id, english_text
                FROM subtitle_lines
                WHERE video_id = ? AND TRIM(chinese_text) = ''
                ORDER BY line_index
                """,
                (video_id,),
            ).fetchall()
        ]
        if not rows:
            update_chinese_translation_status(db, video_id, "complete")
            return
        update_chinese_translation_status(db, video_id, "running")

    updated_count = 0
    chunk_size = 2
    for chunk_start in range(0, len(rows), chunk_size):
        chunk = rows[chunk_start : chunk_start + chunk_size]
        translations = translate_caption_chunk(
            [{"text": row["english_text"]} for row in chunk],
        )
        with connect() as db:
            for row, translation in zip(chunk, translations):
                cleaned = str(translation or "").strip()
                if not cleaned:
                    continue
                updated_count += 1
                db.execute(
                    """
                    UPDATE subtitle_lines
                    SET chinese_text = ?
                    WHERE id = ?
                    """,
                    (cleaned, row["id"]),
                )
            update_chinese_translation_status(db, video_id, "running")

    with connect() as db:
        counts = subtitle_translation_counts(db, video_id)
        if counts["total"] and counts["translated"] >= counts["total"]:
            update_chinese_translation_status(db, video_id, "complete")
        elif updated_count:
            update_chinese_translation_status(
                db,
                video_id,
                "partial",
                "部分中文字幕生成失败，可稍后重新生成。",
            )
        else:
            update_chinese_translation_status(
                db,
                video_id,
                "failed",
                "中文字幕生成失败，请稍后重试。",
            )


def fetch_youtube_video(url: str) -> ImportedVideo:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="请粘贴有效的 YouTube 视频链接")

    info = fetch_video_info_with_fallback(video_id)
    duration_seconds = int(info.get("duration_seconds") or 0)
    if duration_seconds and duration_seconds > MAX_VIDEO_SECONDS:
        raise HTTPException(status_code=400, detail="MVP 版本目前只支持 1 小时以内的视频")

    english_lines: list[dict[str, Any]] = []
    chinese_lines: list[dict[str, Any]] = []

    try:
        english_lines, chinese_lines = fetch_transcript_caption_lines(video_id)
        if english_lines:
            print(f"[youtube transcript] loaded {len(english_lines)} lines for {video_id}", flush=True)
    except Exception as error:
        print(f"[youtube transcript failed] {type(error).__name__}: {error}", flush=True)

    if not english_lines:
        try:
            english_lines = fetch_supadata_english_lines(video_id)
            if english_lines:
                print(f"[supadata transcript fallback] loaded {len(english_lines)} lines for {video_id}", flush=True)
                info = merge_video_info(info, fetch_supadata_video_info(video_id))
        except Exception as error:
            print(f"[supadata transcript failed] {type(error).__name__}: {error}", flush=True)

    if not english_lines:
        try:
            try:
                from yt_dlp import YoutubeDL
            except ImportError as import_error:
                raise HTTPException(status_code=500, detail="YouTube 解析依赖未安装") from import_error

            ydl_options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "extract_flat": False,
                "cachedir": False,
            }
            try:
                with YoutubeDL(ydl_options) as ydl:
                    ytdlp_info = ydl.extract_info(normalized_youtube_url(video_id), download=False)
                info = merge_video_info(
                    info,
                    {
                        "title": ytdlp_info.get("title"),
                        "channel": ytdlp_info.get("channel") or ytdlp_info.get("uploader"),
                        "duration_seconds": parse_duration_seconds(ytdlp_info.get("duration")),
                        "thumbnail": ytdlp_info.get("thumbnail"),
                        "description": ytdlp_info.get("description") or "",
                    },
                )
                duration_seconds = int(info.get("duration_seconds") or 0)
                if duration_seconds and duration_seconds > MAX_VIDEO_SECONDS:
                    raise HTTPException(status_code=400, detail="MVP 版本目前只支持 1 小时以内的视频")

                subtitle_tracks = ytdlp_info.get("subtitles") or {}
                automatic_tracks = ytdlp_info.get("automatic_captions") or {}
                english_track = choose_caption_track(subtitle_tracks, ("en",)) or choose_caption_track(
                    automatic_tracks,
                    ("en",),
                )
                if not english_track:
                    raise HTTPException(
                        status_code=400,
                        detail="这个视频没有可读取的英文字幕。请换一个开启英文字幕的视频。",
                    )
                english_lines = fetch_caption_entries(english_track)
                chinese_lines = []
            except HTTPException:
                raise
            except Exception as caption_error:
                print(f"[yt-dlp caption fallback failed] {type(caption_error).__name__}: {caption_error}", flush=True)
                raise HTTPException(
                    status_code=502,
                    detail="暂时无法读取这个视频的字幕。请换一个开启英文字幕的视频，或稍后再试。",
                ) from caption_error
        except HTTPException:
            raise

    english_lines = [
        line for line in english_lines
        if line.get("text")
        and not is_caption_noise(str(line.get("text", "")))
        and float(line.get("end_seconds", 0)) > float(line.get("start_seconds", 0))
    ]
    if not english_lines:
        raise HTTPException(status_code=400, detail="英文字幕为空。请换一个字幕内容更完整的视频。")

    english_lines = merge_caption_fragments(english_lines)
    chinese_lines = merge_caption_fragments(chinese_lines)

    if chinese_lines:
        translations = [match_translation_range(line, chinese_lines) for line in english_lines]
    else:
        # Keep video import fast and reliable. Chinese generation can be added as a
        # follow-up enhancement, but it should not block playback and English captions.
        translations = [""] * len(english_lines)

    subtitles = [
        ImportedSubtitle(
            start_seconds=float(line["start_seconds"]),
            end_seconds=float(line["end_seconds"]),
            en=str(line["text"]),
            zh=translations[index] if index < len(translations) else "",
        )
        for index, line in enumerate(english_lines)
    ]

    duration_seconds = int(info.get("duration_seconds") or 0)
    summary = clean_caption_text(info.get("description") or "")[:700]
    return ImportedVideo(
        youtube_url=normalized_youtube_url(video_id),
        youtube_video_id=video_id,
        title=str(info.get("title") or "YouTube Video"),
        channel=str(info.get("channel") or "Unknown"),
        duration=format_seconds(duration_seconds) if duration_seconds else format_seconds(subtitles[-1].end_seconds),
        thumbnail_url=str(info.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"),
        summary=summary or "Imported from YouTube captions.",
        subtitles=subtitles,
    )


def mock_chat_reply(db: sqlite3.Connection, video_id: int, message: str) -> str:
    video = get_video_or_404(db, video_id)
    lowered = message.lower()
    if any(word in lowered for word in ["learn", "学", "学到", "表达"]):
        return (
            "Good. Try turning that learning into one sentence you can reuse. "
            "For this video, a useful pattern is: 'The real shift happens when...'."
        )
    if any(word in lowered for word in ["summary", "概述", "main", "主要"]):
        return (
            f"The main idea of '{video['title']}' is that English becomes easier "
            "when you connect it directly with meaning instead of translating word by word."
        )
    return (
        "That is a good starting point. Can you connect your answer to one specific "
        "sentence from the video, then say whether you agree with it?"
    )


def subtitles_context(db: sqlite3.Connection, video_id: int, max_chars: int = 12000) -> str:
    rows = db.execute(
        """
        SELECT start_time, english_text, chinese_text
        FROM subtitle_lines
        WHERE video_id = ?
        ORDER BY line_index
        """,
        (video_id,),
    ).fetchall()
    lines = [
        f"{row['start_time']} EN: {row['english_text']}\nZH: {row['chinese_text']}"
        for row in rows
    ]
    context = "\n".join(lines)
    if len(context) <= max_chars:
        return context

    head_count = min(80, max(20, len(lines) // 4))
    tail_count = min(40, max(12, len(lines) // 8))
    middle_count = min(40, max(12, len(lines) // 8))
    middle_start = max(head_count, len(lines) // 2 - middle_count // 2)
    sampled = [
        *lines[:head_count],
        "[... middle of transcript omitted for length ...]",
        *lines[middle_start : middle_start + middle_count],
        "[... later transcript omitted for length ...]",
        *lines[-tail_count:],
    ]
    return "\n".join(sampled)[:max_chars]


def build_ai_chat_reply(db: sqlite3.Connection, video_id: int, message: str) -> str:
    video = get_video_or_404(db, video_id)
    context = subtitles_context(db, video_id)
    try:
        return call_builder_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an English learning conversation partner for a Chinese learner. "
                        "Discuss the current YouTube video. Keep replies concise, natural, and "
                        "easy to answer orally. Use English by default, but include brief Chinese "
                        "support when it helps comprehension. Do not grade pronunciation."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Video title: {video['title']}\n"
                        f"Video summary: {video['summary']}\n"
                        f"Subtitles:\n{context}\n\n"
                        f"Learner says: {message}\n\n"
                        "Reply as the AI coach and ask one useful follow-up question."
                    ),
                },
            ],
            max_tokens=360,
        )
    except Exception as error:
        print(f"[builder chat fallback] {type(error).__name__}: {error}", flush=True)
        return mock_chat_reply(db, video_id, message)


def explain_expression_with_builder(expression_text: str, context: str) -> dict[str, str]:
    try:
        raw = call_builder_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You explain English expressions for Chinese learners. "
                        "Return strict JSON only with keys chinese_meaning and note."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Expression: {expression_text}\n"
                        f"Context: {context}\n"
                        "Give a concise Chinese meaning and one short usage note."
                    ),
                },
            ],
            max_tokens=220,
        )
        parsed = parse_json_object(raw)
        return {
            "chinese_meaning": str(parsed.get("chinese_meaning", "")).strip(),
            "note": str(parsed.get("note", "")).strip(),
        }
    except Exception:
        return {
            "chinese_meaning": context or expression_text,
            "note": "mock fallback: builder explanation unavailable",
        }


def translate_text_with_builder(text: str) -> str:
    try:
        return call_builder_chat(
            [
                {
                    "role": "system",
                    "content": "Translate English to concise natural Chinese. Return only the translation.",
                },
                {"role": "user", "content": text},
            ],
            max_tokens=220,
        )
    except Exception:
        return f"（mock 翻译）{text}"


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS videos (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              youtube_url TEXT UNIQUE NOT NULL,
              title TEXT NOT NULL,
              channel TEXT NOT NULL,
              duration TEXT NOT NULL,
              thumbnail_tone TEXT NOT NULL DEFAULT 'blue',
              summary TEXT NOT NULL DEFAULT '',
              last_position TEXT NOT NULL DEFAULT '00:00',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS subtitle_lines (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              video_id INTEGER NOT NULL,
              line_index INTEGER NOT NULL,
              start_time TEXT NOT NULL,
              end_time TEXT NOT NULL,
              english_text TEXT NOT NULL,
              chinese_text TEXT NOT NULL,
              FOREIGN KEY (video_id) REFERENCES videos(id)
            );

            CREATE TABLE IF NOT EXISTS expression_cards (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              video_id INTEGER NOT NULL,
              source_type TEXT NOT NULL,
              expression_text TEXT NOT NULL,
              chinese_meaning TEXT NOT NULL,
              context TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (video_id) REFERENCES videos(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              video_id INTEGER NOT NULL,
              role TEXT NOT NULL,
              text TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (video_id) REFERENCES videos(id)
            );
            """
        )
        ensure_column(db, "videos", "youtube_video_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(db, "videos", "thumbnail_url", "TEXT NOT NULL DEFAULT ''")
        ensure_column(
            db,
            "videos",
            "chinese_translation_status",
            "TEXT NOT NULL DEFAULT 'idle'",
        )
        ensure_column(
            db,
            "videos",
            "chinese_translation_error",
            "TEXT NOT NULL DEFAULT ''",
        )


def ensure_column(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        row["name"]
        for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def ensure_mock_video(db: sqlite3.Connection) -> int:
    existing = db.execute(
        "SELECT id FROM videos WHERE youtube_url = ?",
        (MOCK_VIDEO["youtube_url"],),
    ).fetchone()
    if existing:
        return int(existing["id"])

    cursor = db.execute(
        """
        INSERT INTO videos (youtube_url, title, channel, duration, thumbnail_tone, summary, last_position)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            MOCK_VIDEO["youtube_url"],
            MOCK_VIDEO["title"],
            MOCK_VIDEO["channel"],
            MOCK_VIDEO["duration"],
            MOCK_VIDEO["thumbnail_tone"],
            MOCK_VIDEO["summary"],
            "01:03",
        ),
    )
    video_id = int(cursor.lastrowid)
    insert_mock_subtitles(db, video_id)
    return video_id


def upsert_imported_video(db: sqlite3.Connection, imported: ImportedVideo) -> int:
    has_chinese = any(line.zh.strip() for line in imported.subtitles)
    translation_status = "complete" if has_chinese else "idle"
    existing = db.execute(
        """
        SELECT id FROM videos
        WHERE youtube_video_id = ? OR youtube_url = ?
        """,
        (imported.youtube_video_id, imported.youtube_url),
    ).fetchone()

    if existing:
        video_id = int(existing["id"])
        db.execute(
            """
            UPDATE videos
            SET youtube_url = ?,
                youtube_video_id = ?,
                title = ?,
                channel = ?,
                duration = ?,
                thumbnail_url = ?,
                summary = ?,
                chinese_translation_status = ?,
                chinese_translation_error = '',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                imported.youtube_url,
                imported.youtube_video_id,
                imported.title,
                imported.channel,
                imported.duration,
                imported.thumbnail_url,
                imported.summary,
                translation_status,
                video_id,
            ),
        )
        db.execute("DELETE FROM subtitle_lines WHERE video_id = ?", (video_id,))
    else:
        cursor = db.execute(
            """
            INSERT INTO videos (
              youtube_url, youtube_video_id, title, channel, duration, thumbnail_tone,
              thumbnail_url, summary, last_position, chinese_translation_status, chinese_translation_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                imported.youtube_url,
                imported.youtube_video_id,
                imported.title,
                imported.channel,
                imported.duration,
                "blue",
                imported.thumbnail_url,
                imported.summary,
                "00:00",
                translation_status,
                "",
            ),
        )
        video_id = int(cursor.lastrowid)

    for index, line in enumerate(imported.subtitles):
        db.execute(
            """
            INSERT INTO subtitle_lines (
              video_id, line_index, start_time, end_time, english_text, chinese_text
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                index,
                format_seconds(line.start_seconds),
                format_seconds(line.end_seconds),
                line.en,
                line.zh,
            ),
        )
    return video_id


def insert_mock_subtitles(db: sqlite3.Connection, video_id: int) -> None:
    for index, line in enumerate(MOCK_SUBTITLES):
        db.execute(
            """
            INSERT INTO subtitle_lines (
              video_id, line_index, start_time, end_time, english_text, chinese_text
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                index,
                line["start_time"],
                line["end_time"],
                line["en"],
                line["zh"],
            ),
        )


def seed_cards(db: sqlite3.Connection, video_id: int) -> None:
    count = db.execute("SELECT COUNT(*) AS total FROM expression_cards").fetchone()["total"]
    if count:
        return
    for card in SEED_CARDS:
        db.execute(
            """
            INSERT INTO expression_cards (
              video_id, source_type, expression_text, chinese_meaning, context, timestamp, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                card["source_type"],
                card["expression_text"],
                card["chinese_meaning"],
                card["context"],
                card["timestamp"],
                card["note"],
            ),
        )


def get_video_or_404(db: sqlite3.Connection, video_id: int) -> sqlite3.Row:
    video = db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def video_payload(db: sqlite3.Connection, video_id: int) -> dict[str, Any]:
    video = row_to_dict(get_video_or_404(db, video_id))
    subtitles = [
        {
            "id": row["id"],
            "time": row["start_time"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "start_seconds": parse_vtt_timestamp(row["start_time"]),
            "end_seconds": parse_vtt_timestamp(row["end_time"]),
            "en": row["english_text"],
            "zh": row["chinese_text"],
        }
        for row in db.execute(
            """
            SELECT * FROM subtitle_lines
            WHERE video_id = ?
            ORDER BY line_index
            """,
            (video_id,),
        ).fetchall()
    ]
    video["subtitles"] = subtitles
    counts = subtitle_translation_counts(db, video_id)
    video["chinese_translation_total"] = counts["total"]
    video["chinese_translation_count"] = counts["translated"]
    return video


def queue_chinese_translation_if_needed(
    db: sqlite3.Connection,
    video_id: int,
    background_tasks: BackgroundTasks,
) -> None:
    counts = subtitle_translation_counts(db, video_id)
    if not counts["total"] or counts["translated"] >= counts["total"]:
        update_chinese_translation_status(db, video_id, "complete")
        return
    if not has_ai_builder_token():
        update_chinese_translation_status(
            db,
            video_id,
            "failed",
            "当前未连接 Builder API，无法生成中文字幕。",
        )
        return
    video = get_video_or_404(db, video_id)
    if video["chinese_translation_status"] == "running":
        return
    update_chinese_translation_status(db, video_id, "pending")
    background_tasks.add_task(generate_chinese_subtitles_task, video_id)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return {
        "mock_youtube_url": MOCK_URL,
        "builder_enabled": has_ai_builder_token(),
        "supadata_enabled": bool(get_supadata_key()),
        "builder_features": [
            "chat",
            "translation",
            "expression_explanation",
            "audio_transcription",
        ],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/videos/import")
def import_video(request: ImportVideoRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    if request.url == MOCK_URL:
        with connect() as db:
            video_id = ensure_mock_video(db)
            db.execute(
                """
                UPDATE videos
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (video_id,),
            )
            return video_payload(db, video_id)

    imported = fetch_youtube_video(request.url)
    with connect() as db:
        video_id = upsert_imported_video(db, imported)
        queue_chinese_translation_if_needed(db, video_id, background_tasks)
        return video_payload(db, video_id)


@app.get("/api/videos")
def list_videos() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT
              v.*,
              COUNT(c.id) AS expression_count
            FROM videos v
            LEFT JOIN expression_cards c ON c.video_id = v.id
            GROUP BY v.id
            ORDER BY v.updated_at DESC
            """
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/api/videos/{video_id}")
def get_video(video_id: int) -> dict[str, Any]:
    with connect() as db:
        return video_payload(db, video_id)


@app.get("/api/videos/{video_id}/translation-status")
def get_translation_status(video_id: int) -> dict[str, Any]:
    with connect() as db:
        video = get_video_or_404(db, video_id)
        counts = subtitle_translation_counts(db, video_id)
        return {
            "video_id": video_id,
            "status": video["chinese_translation_status"],
            "error": video["chinese_translation_error"],
            "total": counts["total"],
            "translated": counts["translated"],
        }


@app.post("/api/videos/{video_id}/translate-subtitles")
def translate_video_subtitles(video_id: int, background_tasks: BackgroundTasks) -> dict[str, Any]:
    with connect() as db:
        get_video_or_404(db, video_id)
        queue_chinese_translation_if_needed(db, video_id, background_tasks)
        video = get_video_or_404(db, video_id)
        counts = subtitle_translation_counts(db, video_id)
        return {
            "video_id": video_id,
            "status": video["chinese_translation_status"],
            "error": video["chinese_translation_error"],
            "total": counts["total"],
            "translated": counts["translated"],
        }


@app.get("/api/expression-cards")
def list_expression_cards() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT
              c.*,
              v.title AS video_title
            FROM expression_cards c
            JOIN videos v ON v.id = c.video_id
            ORDER BY c.created_at DESC, c.id DESC
            """
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.post("/api/expression-cards")
def create_expression_card(request: ExpressionCardRequest) -> dict[str, Any]:
    with connect() as db:
        get_video_or_404(db, request.video_id)
        chinese_meaning = request.chinese_meaning
        note = request.note
        if not chinese_meaning.strip():
            explanation = explain_expression_with_builder(
                request.expression_text,
                request.context,
            )
            chinese_meaning = explanation["chinese_meaning"]
            note = note or explanation["note"]

        existing = db.execute(
            """
            SELECT * FROM expression_cards
            WHERE video_id = ? AND expression_text = ?
            """,
            (request.video_id, request.expression_text),
        ).fetchone()
        if existing:
            return row_to_dict(existing)

        cursor = db.execute(
            """
            INSERT INTO expression_cards (
              video_id, source_type, expression_text, chinese_meaning, context, timestamp, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.video_id,
                request.source_type,
                request.expression_text,
                chinese_meaning,
                request.context,
                request.timestamp,
                note,
            ),
        )
        card = db.execute(
            "SELECT * FROM expression_cards WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return row_to_dict(card)


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    with connect() as db:
        get_video_or_404(db, request.video_id)
        db.execute(
            "INSERT INTO messages (video_id, role, text) VALUES (?, ?, ?)",
            (request.video_id, "user", request.message),
        )
        reply = build_ai_chat_reply(db, request.video_id, request.message)
        cursor = db.execute(
            "INSERT INTO messages (video_id, role, text) VALUES (?, ?, ?)",
            (request.video_id, "ai", reply),
        )
        return {"id": cursor.lastrowid, "role": "ai", "text": reply}


@app.post("/api/translate")
def translate_text(request: TranslationRequest) -> dict[str, str]:
    return {"text": request.text, "translation": translate_text_with_builder(request.text)}


@app.post("/api/explain-expression")
def explain_expression(request: ExpressionExplainRequest) -> dict[str, str]:
    explanation = explain_expression_with_builder(
        request.expression_text,
        request.context,
    )
    return {"expression_text": request.expression_text, **explanation}


@app.post("/api/audio/transcriptions")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, str]:
    token = get_ai_builder_token()
    if not token:
        raise HTTPException(status_code=503, detail="AI Builder token is not configured")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    files = {
        "file": (
            file.filename or "audio.webm",
            content,
            file.content_type or "application/octet-stream",
        ),
    }
    data = {"model": os.getenv("AI_BUILDER_TRANSCRIPTION_MODEL", AI_BUILDER_TRANSCRIPTION_MODEL)}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=90) as client:
            response = client.post(
                f"{AI_BUILDER_BASE_URL}/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Audio transcription failed: {error}") from error

    text = str(payload.get("text") or payload.get("transcript") or "")
    return {"text": text, "provider": "builder"}


@app.get("/api/videos/{video_id}/messages")
def list_messages(video_id: int) -> list[dict[str, Any]]:
    with connect() as db:
        get_video_or_404(db, video_id)
        rows = db.execute(
            """
            SELECT * FROM messages
            WHERE video_id = ?
            ORDER BY id
            """,
            (video_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")


@app.get("/script.js")
def script() -> FileResponse:
    return FileResponse(STATIC_DIR / "script.js", media_type="application/javascript")


app.mount("/web", StaticFiles(directory=STATIC_DIR), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "youtube_learning_app.main:app",
        host="0.0.0.0",
        port=APP_PORT,
    )
