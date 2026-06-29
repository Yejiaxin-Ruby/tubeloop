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
from fastapi import FastAPI, File, HTTPException, UploadFile
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
MAX_VIDEO_SECONDS = 60 * 60

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
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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
        if not text:
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
            if caption_text:
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


def transcript_snippet_value(snippet: Any, key: str, default: Any = None) -> Any:
    if isinstance(snippet, dict):
        return snippet.get(key, default)
    return getattr(snippet, key, default)


def transcript_to_caption_lines(fetched: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for snippet in fetched:
        text = clean_caption_text(str(transcript_snippet_value(snippet, "text", "")))
        if not text:
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
    translations: list[str] = []
    if not lines:
        return translations
    chunk_size = 35
    for chunk_start in range(0, len(lines), chunk_size):
        chunk = lines[chunk_start : chunk_start + chunk_size]
        numbered = "\n".join(
            f"{index + 1}. {line['text']}"
            for index, line in enumerate(chunk)
        )
        try:
            raw = call_builder_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Translate English subtitle lines into concise, natural Simplified Chinese. "
                            "Return strict JSON array only. The array length must match the input line count."
                        ),
                    },
                    {"role": "user", "content": numbered},
                ],
                max_tokens=2400,
            )
            parsed = [str(item).strip() for item in parse_json_array(raw)]
            if len(parsed) != len(chunk):
                raise ValueError("Translation count mismatch")
            translations.extend(parsed)
        except Exception as error:
            print(f"[subtitle translation fallback] {type(error).__name__}: {error}", flush=True)
            translations.extend([""] * len(chunk))
    return translations


def fetch_youtube_video(url: str) -> ImportedVideo:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="请粘贴有效的 YouTube 视频链接")

    try:
        from yt_dlp import YoutubeDL
    except ImportError as error:
        raise HTTPException(status_code=500, detail="YouTube 解析依赖未安装") from error

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
            info = ydl.extract_info(normalized_youtube_url(video_id), download=False)
    except Exception as error:
        print(f"[youtube metadata failed] {type(error).__name__}: {error}", flush=True)
        raise HTTPException(
            status_code=502,
            detail="暂时无法读取这个 YouTube 视频。请确认链接可公开访问，并稍后再试。",
        ) from error

    duration_seconds = int(info.get("duration") or 0)
    if duration_seconds and duration_seconds > MAX_VIDEO_SECONDS:
        raise HTTPException(status_code=400, detail="MVP 版本目前只支持 1 小时以内的视频")

    try:
        english_lines, chinese_lines = fetch_transcript_caption_lines(video_id)
    except Exception as error:
        print(f"[transcript fallback] {type(error).__name__}: {error}", flush=True)
        subtitle_tracks = info.get("subtitles") or {}
        automatic_tracks = info.get("automatic_captions") or {}
        english_track = choose_caption_track(subtitle_tracks, ("en",)) or choose_caption_track(
            automatic_tracks,
            ("en",),
        )
        if not english_track:
            raise HTTPException(
                status_code=400,
                detail="这个视频没有可读取的英文字幕。请换一个开启英文字幕的视频。",
            ) from error
        try:
            english_lines = fetch_caption_entries(english_track)
        except Exception as caption_error:
            print(f"[english caption failed] {type(caption_error).__name__}: {caption_error}", flush=True)
            raise HTTPException(
                status_code=502,
                detail="英文字幕读取失败。请换一个开启英文字幕的视频，或稍后再试。",
            ) from caption_error
        chinese_lines = []

    english_lines = [
        line for line in english_lines
        if line.get("text") and float(line.get("end_seconds", 0)) > float(line.get("start_seconds", 0))
    ]
    if not english_lines:
        raise HTTPException(status_code=400, detail="英文字幕为空。请换一个字幕内容更完整的视频。")

    if chinese_lines:
        translations = [match_translation_line(line, chinese_lines) for line in english_lines]
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

    summary = clean_caption_text(info.get("description") or "")[:700]
    return ImportedVideo(
        youtube_url=normalized_youtube_url(video_id),
        youtube_video_id=video_id,
        title=str(info.get("title") or "Untitled YouTube video"),
        channel=str(info.get("channel") or info.get("uploader") or "YouTube"),
        duration=format_seconds(duration_seconds) if duration_seconds else format_seconds(subtitles[-1].end_seconds),
        thumbnail_url=str(info.get("thumbnail") or ""),
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
                video_id,
            ),
        )
        db.execute("DELETE FROM subtitle_lines WHERE video_id = ?", (video_id,))
    else:
        cursor = db.execute(
            """
            INSERT INTO videos (
              youtube_url, youtube_video_id, title, channel, duration, thumbnail_tone,
              thumbnail_url, summary, last_position
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    return video


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return {
        "mock_youtube_url": MOCK_URL,
        "builder_enabled": has_ai_builder_token(),
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
def import_video(request: ImportVideoRequest) -> dict[str, Any]:
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
