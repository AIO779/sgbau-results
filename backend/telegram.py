"""
telegram.py — Telegram notification helpers for the Result Watcher.

Uses Python's built-in urllib only — no third-party Telegram library needed.
The two public functions (send_message, send_document) are synchronous and
must be called from async code via asyncio.get_event_loop().run_in_executor().

Telegram Bot API endpoints used:
  POST https://api.telegram.org/bot{TOKEN}/sendMessage
  POST https://api.telegram.org/bot{TOKEN}/sendDocument
"""

import io
import json
import logging
import os
import urllib.parse
import urllib.request
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ── Telegram API base ──────────────────────────────────────────────────────────

_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_bot_token() -> str:
    """Read TELEGRAM_BOT_TOKEN from environment. Raises if missing."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")
    # Strip accidental quotes and whitespace
    token = token.strip(" '\"")
    # If the user accidentally included the 'bot' prefix, remove it
    if token.lower().startswith("bot"):
        token = token[3:]
    return token


def _get_chat_id() -> str:
    """Read TELEGRAM_CHAT_ID from environment. Raises if missing."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is not configured.")
    return chat_id.strip(" '\"")


def _escape_mdv2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    Required characters: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


# ── Public functions ───────────────────────────────────────────────────────────

def send_message(text: str) -> bool:
    """
    Send a plain-text (MarkdownV2) message to the admin Telegram chat.

    Returns True on success, False on failure (logs the reason).
    Synchronous — call via run_in_executor() from async code.
    """
    try:
        token   = _get_bot_token()
        chat_id = _get_chat_id()
        url     = _TG_BASE.format(token=token, method="sendMessage")

        payload = urllib.parse.urlencode({
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": "MarkdownV2",
        }).encode("utf-8")

        req  = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())
            if not body.get("ok"):
                logger.error("Telegram sendMessage failed: %s", body)
                return False
        return True

    except Exception as exc:
        logger.error("send_message raised: %s", exc)
        return False


def send_document(filename: str, file_bytes: bytes, caption: str) -> bool:
    """
    Send a file (the results CSV) as a Telegram document attachment.

    Builds a multipart/form-data request using Python's email.mime module
    (same technique browsers use for file uploads).

    Returns True on success, False on failure.
    Synchronous — call via run_in_executor() from async code.
    """
    try:
        token   = _get_bot_token()
        chat_id = _get_chat_id()
        url     = _TG_BASE.format(token=token, method="sendDocument")

        # Build multipart/form-data body
        outer = MIMEMultipart("form-data")

        def _field(name: str, value: str) -> MIMEBase:
            part = MIMEBase("text", "plain")
            part.add_header("Content-Disposition", "form-data", name=name)
            part.set_payload(value)
            return part

        outer.attach(_field("chat_id", chat_id))
        outer.attach(_field("caption", caption))

        # File part
        file_part = MIMEBase("application", "octet-stream")
        file_part.add_header(
            "Content-Disposition", "form-data",
            name="document", filename=filename,
        )
        file_part.set_payload(file_bytes)
        outer.attach(file_part)

        # Extract boundary and raw body from the MIME object
        content_type = outer["Content-Type"]           # multipart/form-data; boundary=...
        # email.mime uses \n line endings; HTTP expects \r\n
        raw_body = outer.as_bytes().split(b"\n\n", 1)[1].replace(b"\n", b"\r\n")

        req = urllib.request.Request(
            url,
            data=raw_body,
            method="POST",
            headers={"Content-Type": content_type},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            if not body.get("ok"):
                logger.error("Telegram sendDocument failed: %s", body)
                return False
        return True

    except Exception as exc:
        logger.error("send_document raised: %s", exc)
        return False


# ── Notification orchestrator ──────────────────────────────────────────────────

def build_notification_text(summaries: list, state: dict) -> str:
    """
    Build the MarkdownV2-formatted Telegram message body.

    Uses summary data (total/passed/failed) and state config
    (dept_name, session, sem_code, result_type, roll range).
    """
    # Session label map (same values as index.html dropdowns)
    SESSION_LABELS = {
        "SE08": "Summer 2018", "SE09": "Winter 2018",
        "SE10": "Summer 2019", "SE11": "Winter 2019",
        "SE12": "Summer 2020", "SE13": "Winter 2020",
        "SE14": "Summer 2021", "SE15": "Winter 2021",
        "SE16": "Summer 2022", "SE17": "Winter 2022",
        "SE18": "Summer 2023", "SE19": "Winter 2023",
        "SE20": "Summer 2024", "SE21": "Winter 2024",
        "SE22": "Summer 2025", "SE23": "Winter 2025",
        "SE24": "Summer 2026", "SE25": "Winter 2026",
    }
    SEM_LABELS = {
        "SM01": "Sem 1", "SM02": "Sem 2", "SM03": "Sem 3",
        "SM04": "Sem 4", "SM05": "Sem 5", "SM06": "Sem 6",
        "SM07": "Sem 7", "SM08": "Sem 8", "SM09": "Sem 9",
        "SM10": "Sem 10", "SM17": "First Year", "SM18": "Second Year",
        "SM19": "Third Year", "SM20": "Fourth Year",
    }
    RESULT_TYPE_LABELS = {"R": "Regular", "B": "Back", "RV": "Reval", "EV": "EVS"}

    session_code  = state.get("session", "")
    sem_code      = state.get("sem_code", "")
    result_type   = state.get("result_type", "")
    dept_name     = state.get("dept_name", "")
    start_roll    = state.get("start_roll", "")
    end_roll      = state.get("end_roll", "")

    session_label  = SESSION_LABELS.get(session_code, session_code)
    sem_label      = SEM_LABELS.get(sem_code, sem_code)
    rt_label       = RESULT_TYPE_LABELS.get(result_type, result_type)

    # Aggregate across all departments (usually just one for watcher)
    total  = sum(s.get("total",  0) for s in summaries)
    passed = sum(s.get("passed", 0) for s in summaries)
    failed = total - passed
    pct    = (passed / total * 100) if total > 0 else 0.0

    # MarkdownV2 escaping
    e = _escape_mdv2

    lines = [
        "🔔 *SGBAU Results Declared\\!*",
        "",
        f"🏛️ *Department:* {e(dept_name)}",
        f"📅 *Session:* {e(session_label)} \\({e(session_code)}\\)",
        f"📖 *Semester:* {e(sem_label)} \\({e(sem_code)}\\)",
        f"📋 *Result Type:* {e(rt_label)}",
        f"📊 *Range:* `{e(start_roll)}` → `{e(end_roll)}`",
        "",
        f"✅ *Total Fetched:* {e(str(total))} students",
        f"🎓 *Passed:* {e(str(passed))} \\({e(f'{pct:.1f}')}%\\)",
        f"❌ *Failed:* {e(str(failed))} \\({e(f'{100-pct:.1f}')}%\\)",
        "",
        "📎 Full results CSV is attached below\\.",
        "",
        "— SGBAU Result Watcher \\(auto\\-sent\\)",
    ]
    return "\n".join(lines)


async def send_results_notification(summaries: list, state: dict) -> str:
    """
    Async orchestrator called by run_watcher_loop() after batch fetch.

    1. Builds the MarkdownV2 message text
    2. Calls send_message() via run_in_executor (non-blocking)
    3. Builds CSV filename + caption
    4. Calls send_document() via run_in_executor (non-blocking)

    Returns the TELEGRAM_CHAT_ID string (used by the caller to push SSE event).
    The CSV bytes are passed in by the caller via JOBS dict (see Phase 8).
    """
    import asyncio  # noqa: PLC0415

    loop    = asyncio.get_event_loop()
    chat_id = _get_chat_id()   # validate early — raises if not configured

    text = build_notification_text(summaries, state)
    await loop.run_in_executor(None, send_message, text)

    # Build CSV in memory and send
    try:
        from backend.watcher import build_csv_bytes  # noqa: PLC0415
        from backend.main import JOBS                # noqa: PLC0415

        # Collect all_results from JOBS (populated by run_batch_fetch)
        watcher_id  = state.get("watcher_id", "")
        job         = JOBS.get(watcher_id, {})
        all_results = job.get("results", [])
        reports     = job.get("reports", {})

        csv_bytes = build_csv_bytes(all_results, reports)

        dept      = state.get("dept_name", "dept")
        session   = state.get("session", "")
        sem       = state.get("sem_code", "")
        filename  = f"sgbau_{dept}_results_{session}_{sem}.csv"
        caption   = f"📊 Full results for {dept} — {session}, {sem}"

        await loop.run_in_executor(None, send_document, filename, csv_bytes, caption)

    except Exception as exc:
        logger.error("send_results_notification: CSV send failed — %s", exc)

    return chat_id
