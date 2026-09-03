"""
watcher.py — State-file persistence layer for the Result Watcher.

Provides a constant and five helpers that every other watcher module
uses to read, write, and delete `watcher_state.json`.

State file schema (see phases_01_02_03.md § 3.3 for full reference):
  {
    "watcher_id":       str  (UUID),
    "dept_name":        str,
    "start_roll":       str,
    "end_roll":         str,
    "sentinel_roll":    str,
    "interval_minutes": int,
    "session":          str,
    "course_type":      str,
    "result_type":      str,
    "sem_code":         str,
    "course_cd":        str,
    "status":           "WAITING" | "FETCHING" | "DONE" | "CANCELLED",
    "probe_count":      int,
    "last_probe_time":  str | null,
    "next_probe_time":  str | null,
    "created_at":       str,
    "cancelled":        bool
  }
"""

import csv
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# ── Constant ───────────────────────────────────────────────────────────────────

STATE_FILE = "backend/watcher_state.json"


# ── Helper functions ───────────────────────────────────────────────────────────

def state_exists() -> bool:
    """
    Return True if the state file is present on disk, False otherwise.

    Called by:
      - The startup auto-resume hook (to decide whether to resume a watcher)
      - POST /api/watch/start (to prevent duplicate watchers)
    """
    return os.path.exists(STATE_FILE)


def read_state() -> dict | None:
    """
    Load and parse the state file.

    Returns:
      dict  — the parsed JSON on success.
      None  — if the file does not exist or the JSON is corrupted.

    Called by:
      - The startup auto-resume hook
      - GET /api/watch/current
      - The SSE stream
      - The polling loop (after every probe)
    """
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("read_state: could not load state file — %s", exc)
        return None


def write_state(data: dict) -> None:
    """
    Write *data* as the complete contents of the state file.

    Uses default=str so datetime objects are safely serialised.

    Called by:
      - POST /api/watch/start (initial creation)
      - update_state() (after every patch)
    """
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def update_state(**kwargs) -> None:
    """
    Merge keyword arguments into the existing state file and persist.

    Example:
      update_state(probe_count=4, status="FETCHING")

    If read_state() returns None (file was deleted concurrently or
    corrupted), the function does nothing to avoid overwriting stale data.

    Called by:
      - The polling loop after every probe
      - Whenever the watcher status changes
    """
    current = read_state()
    if current is None:
        logger.warning("update_state: state file missing or corrupt — skipping update")
        return
    current.update(kwargs)
    write_state(current)


def delete_state() -> None:
    """
    Remove the state file from disk if it exists.

    Called by:
      - The polling loop when it exits (status DONE or CANCELLED)
    """
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logger.info("Watcher state file deleted.")


# ── Phase 4 & 8: Core polling loop + CSV generation ───────────────────────────

import asyncio                              # noqa: E402
import io                                   # noqa: E402
import aiohttp                              # noqa: E402
from datetime import datetime, timedelta    # noqa: E402


def build_csv_bytes(results_or_path, reports: dict) -> bytes:
    """
    Phase 8.2 — Build the results CSV in memory as bytes.

    Applies the same column-filtering logic as the existing
    GET /api/download/{job_id} route so both produce identical output.

    Args:
      results_or_path — either a list of result dicts OR a str path to
                         a .jsonl temp file (Phase 5). Both are supported.
      reports         — { dept_name: class_report_dict } from scrape_departments()

    Returns:
      UTF-8 encoded bytes of the complete CSV (data rows + class report).
    """
    from backend.utils import format_class_report          # noqa: PLC0415

    # Phase 5: accept either a file path or an in-memory list
    if isinstance(results_or_path, str):
        results = []
        if os.path.exists(results_or_path):
            with open(results_or_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        results.append(json.loads(line))
    else:
        results = results_or_path

    if not results:
        return b"No results collected.\n"

    # Columns to always exclude (internal metadata)
    _EXCLUDE = {
        "Status", "Error", "Department", "Roll Number", "PRN",
        "Session", "Message", "Max Marks",
        "Subject", "Paper", "THEORY", "I.A.", "I.A.(PRAC)", "PRACTICAL",
        "Abbreviation", "Marks Scored", "Grade Point", "Grade", "Remarks", "Credits",
    }
    FIXED     = ["Roll No", "Name", "Result", "SGPA", "College"]
    fixed_set = set(FIXED)

    # Collect all keys present in results (preserves insertion order)
    all_keys: dict = {}
    for row in results:
        for k in row:
            if k not in all_keys:
                all_keys[k] = True

    subj_cols = [
        c for c in all_keys
        if c not in _EXCLUDE and c not in fixed_set and " " not in c
    ]
    ordered = [c for c in FIXED if c in all_keys] + subj_cols

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=ordered, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(results)

    if reports:
        buf.write("\n")
        for dept_name, rpt in reports.items():
            buf.write(format_class_report(rpt))
            buf.write("\n")

    return buf.getvalue().encode("utf-8")


async def run_batch_fetch(watcher_id: str) -> list:
    """
    When the sentinel probe returns declared, perform the full batch fetch.

    Steps:
      1. Read state → extract dept config and roll range
      2. Push { type: "fetching" } SSE event
      3. Build a DeptRequest and call the existing scrape_departments()
      4. Pipe every result back to the SSE queue via progress_callback
      5. Store results + reports in JOBS[watcher_id] (Phase 8.4 Option A)
         so GET /api/download/{watcher_id} works with zero route changes
      6. Return the summaries list

    On partial failure: stores whatever was collected before the exception,
    still returns partial summaries (never raises).
    """
    # Lazy imports to avoid circular imports at module load time
    from backend.main import WATCHERS, JOBS                # noqa: PLC0415
    from backend.scraper import scrape_departments         # noqa: PLC0415
    from backend.models import DeptRequest                 # noqa: PLC0415

    state  = read_state()
    queue: asyncio.Queue = WATCHERS[watcher_id]["queue"]

    if not state:
        await queue.put({"type": "error", "message": "State file missing before batch fetch."})
        return []

    start_roll = state["start_roll"]
    end_roll   = state["end_roll"]
    dept_name  = state["dept_name"]

    # Estimate roll count for the SSE fetching message
    import re  # noqa: PLC0415
    m_s = re.match(r'^(.*?)(\d+)$', start_roll)
    m_e = re.match(r'^(.*?)(\d+)$', end_roll)
    roll_count = abs(int(m_e.group(2)) - int(m_s.group(2))) + 1 if (m_s and m_e) else "?"

    await queue.put({
        "type":        "fetching",
        "total_rolls": roll_count,
        "range":       f"{start_roll} → {end_roll}",
        "message":     f"Fetching {roll_count} rolls...",
    })

    dept_req = DeptRequest(
        name=dept_name,
        start_roll=start_roll,
        end_roll=end_roll,
        course_cd=state["course_cd"],
    )

    # Phase 5: create temp file for streaming results to disk
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", prefix=f"sgbau_watcher_{watcher_id}_",
        delete=False, encoding="utf-8",
    )
    # Pre-register a JOBS entry so the download endpoint can serve results
    JOBS[watcher_id] = {
        "queue":        queue,
        "results_file": tmp.name,   # Phase 5: file path instead of in-memory list
        "reports":      {},
        "done":         False,
        "error":        None,
    }

    count = 0
    summaries: list = []

    async def progress_callback(dept: str, result: dict):
        nonlocal count
        count += 1
        # Phase 5: write to temp file instead of growing list in memory
        tmp.write(json.dumps({**result, "Department": dept}) + "\n")
        tmp.flush()
        await queue.put({
            "type":   "result",
            "dept":   dept,
            "roll":   result.get("Roll No", ""),
            "name":   result.get("Name", ""),
            "result": result.get("Result", result.get("Status", "")),
            "sgpa":   result.get("SGPA", ""),
            "status": result.get("Status", ""),
            "count":  count,
        })

    # Phase 4: emit retry events to the watcher SSE stream
    async def retry_callback(roll: str, attempt: int):
        await queue.put({
            "type":    "retry",
            "roll":    roll,
            "attempt": attempt,
            "message": f"Server slow, retrying roll {roll} (attempt {attempt})…",
        })

    try:
        summaries = await scrape_departments(
            departments=[dept_req],
            session_val=state["session"],
            course_type=state["course_type"],
            result_type=state["result_type"],
            sem_code=state["sem_code"],
            workers=10,             # Phase 4: reduced from 50 — gentler on SGBAU during peak
            progress_callback=progress_callback,
            retry_callback=retry_callback,           # Phase 4
        )
        # Store class reports into JOBS for CSV download
        for s in summaries:
            if "class_report" in s:
                JOBS[watcher_id]["reports"][s["name"]] = s["class_report"]

    except Exception as exc:
        logger.error("run_batch_fetch: scrape failed mid-way — %s", exc)
        await queue.put({
            "type":    "error",
            "message": f"Batch fetch failed: {exc}",
        })
        # Partial results are in the temp file — Telegram will note this

    finally:
        tmp.close()     # flush & close the temp file

    JOBS[watcher_id]["done"] = True
    return summaries


async def run_watcher_loop(watcher_id: str) -> None:
    """
    The core background polling loop.

    Reads all config from the state file at the start of every iteration
    (survives server restarts cleanly). Never raises — all exceptions are
    caught and pushed as { type: "error" } SSE events.

    Loop steps:
      1. Check cancellation flags (in-memory + state file)
      2. Probe the sentinel roll via fetch_one()
      3a. Not declared → update state, push probe event, sleep (chunked)
      3b. Declared → push probe event, run_batch_fetch, send Telegram,
          push done event, delete state, exit
    """
    # Lazy imports to avoid circular imports at module load time
    from backend.main import WATCHERS                          # noqa: PLC0415
    from backend.scraper import init_session, fetch_one        # noqa: PLC0415

    logger.info("Watcher loop started: %s", watcher_id)

    try:
        while True:
            # ── Step 1: Cancellation check ─────────────────────────────────
            mem_cancelled   = WATCHERS.get(watcher_id, {}).get("cancelled", False)
            state           = read_state()
            file_cancelled  = (state or {}).get("cancelled", False)

            if mem_cancelled or file_cancelled:
                queue: asyncio.Queue = WATCHERS[watcher_id]["queue"]
                await queue.put({"type": "cancelled", "message": "Watcher stopped by admin."})
                update_state(status="CANCELLED")
                delete_state()
                logger.info("Watcher %s cancelled.", watcher_id)
                return

            if not state:
                logger.error("Watcher %s: state file missing mid-loop. Aborting.", watcher_id)
                return

            queue: asyncio.Queue = WATCHERS[watcher_id]["queue"]

            # ── Step 2: Probe the sentinel roll ────────────────────────────
            probe_count = state.get("probe_count", 0) + 1
            sentinel    = state["sentinel_roll"]
            now_str     = datetime.utcnow().isoformat(timespec="seconds")

            try:
                ua = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                }
                semaphore = asyncio.Semaphore(1)

                async with aiohttp.ClientSession(headers=ua) as http:
                    token = await init_session(http)
                    if not token:
                        raise RuntimeError("Failed to fetch CSRF token from SGBAU site.")

                    # Phase 3: wrap token in holder so fetch_one can auto-refresh on 419
                    token_holder: dict = {"token": token, "lock": asyncio.Lock()}

                    probe_result = await fetch_one(
                        http         = http,
                        token_holder = token_holder,
                        roll         = sentinel,
                        semaphore    = semaphore,
                        course_cd    = state["course_cd"],
                        session_val  = state["session"],
                        course_type  = state["course_type"],
                        result_type  = state["result_type"],
                        sem_code     = state["sem_code"],
                    )

                probe_status = probe_result.get("Status", "")
                exam_result  = probe_result.get("Result", "")
                declared = (
                    probe_status == "OK"
                    and exam_result in ("PASS", "FAIL", "ATKT")
                )

            except Exception as exc:
                # Transient network error — log and treat as not declared
                logger.warning("Watcher %s probe #%d error: %s", watcher_id, probe_count, exc)
                await queue.put({
                    "type":      "probe_error",
                    "attempt":   probe_count,
                    "timestamp": now_str,
                    "message":   f"Probe #{probe_count} failed: {exc}. Will retry next cycle.",
                })
                update_state(probe_count=probe_count, last_probe_time=now_str)
                declared = False
                probe_result = {}

            # ── Step 3a: Not declared → sleep and loop ─────────────────────
            if not declared:
                interval = state["interval_minutes"]
                next_time = (
                    datetime.utcnow() + timedelta(minutes=interval)
                ).isoformat(timespec="seconds")

                update_state(
                    probe_count=probe_count,
                    last_probe_time=now_str,
                    next_probe_time=next_time,
                    status="WAITING",
                )

                await queue.put({
                    "type":                "probe",
                    "attempt":             probe_count,
                    "roll":                sentinel,
                    "timestamp":           now_str,
                    "found":               False,
                    "next_probe_in_minutes": interval,
                    "message": (
                        f"Probe #{probe_count}: Not declared yet. "
                        f"Next check in {interval} minutes."
                    ),
                })

                # Cancellation-aware chunked sleep (30-second slices)
                total_sleep = interval * 60
                elapsed     = 0
                while elapsed < total_sleep:
                    await asyncio.sleep(30)
                    elapsed += 30
                    if WATCHERS.get(watcher_id, {}).get("cancelled", False):
                        break

                continue  # loop back to top

            # ── Step 3b: Declared → batch fetch + Telegram + done ──────────
            logger.info("Watcher %s: result DECLARED on probe #%d!", watcher_id, probe_count)

            update_state(
                probe_count=probe_count,
                last_probe_time=now_str,
                status="FETCHING",
            )

            await queue.put({
                "type":      "probe",
                "attempt":   probe_count,
                "roll":      sentinel,
                "timestamp": now_str,
                "found":     True,
                "message":   f"Probe #{probe_count}: RESULT DECLARED! Triggering full batch fetch...",
            })

            summaries = await run_batch_fetch(watcher_id)

            # Send Telegram notification (telegram.py — implemented in Phase 7)
            try:
                from backend.telegram import send_results_notification  # noqa: PLC0415
                chat_id = await send_results_notification(summaries, state)
                await queue.put({
                    "type":       "emailed",
                    "to_chat_id": str(chat_id),
                    "message":    "Telegram notification sent to admin.",
                })
            except ImportError:
                logger.warning("telegram.py not yet implemented — skipping notification.")
            except Exception as tg_exc:
                logger.error("Telegram send failed: %s", tg_exc)

            # Build done summary
            sse_summary = [
                {
                    "name":   s["name"],
                    "range":  s["range"],
                    "total":  s["total"],
                    "passed": s["passed"],
                }
                for s in summaries
            ]

            update_state(status="DONE")
            await queue.put({
                "type":    "done",
                "summary": sse_summary,
                "message": "All done! Results fetched and sent via Telegram.",
            })

            delete_state()
            logger.info("Watcher %s finished cleanly.", watcher_id)
            return

    except Exception as exc:
        logger.exception("Watcher %s loop crashed: %s", watcher_id, exc)
        try:
            queue = WATCHERS[watcher_id]["queue"]
            await queue.put({"type": "error", "message": str(exc)})
        except Exception:
            pass
