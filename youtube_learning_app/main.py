from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

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


def subtitles_context(db: sqlite3.Connection, video_id: int) -> str:
    rows = db.execute(
        """
        SELECT start_time, english_text, chinese_text
        FROM subtitle_lines
        WHERE video_id = ?
        ORDER BY line_index
        """,
        (video_id,),
    ).fetchall()
    return "\n".join(
        f"{row['start_time']} EN: {row['english_text']}\nZH: {row['chinese_text']}"
        for row in rows
    )


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
        video_id = ensure_mock_video(db)
        seed_cards(db, video_id)


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
    # MVP behavior: any YouTube-looking URL maps to the mock learning material.
    if "youtube.com" not in request.url and "youtu.be" not in request.url:
        raise HTTPException(status_code=400, detail="Please use a YouTube URL for this MVP")

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
