"""
main.py — FastAPI application.
Routes: POST /api/fetch-results, GET /api/progress/{job_id},
        GET /api/download/{job_id}, GET /api/health
        POST /api/watch/start, POST /api/watch/verify-pin,
        GET  /api/watch/current, POST /api/watch/stop
"""

import asyncio
import hmac
import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncGenerator

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from backend.models import (
    FetchRequest,
    FetchResponse,
    PinVerifyRequest,
    PinVerifyResponse,
    WatchCurrentResponse,
    WatchRequest,
    WatchStartResponse,
)
from backend.scraper import scrape_departments
from backend.utils import format_class_report
from backend.watcher import (
    delete_state,
    read_state,
    run_watcher_loop,
    state_exists,
    update_state,
    write_state,
)

# ── Lifespan: startup auto-resume hook (Phase 3 §3.6) ─────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: check for a leftover watcher_state.json.
      - DONE / CANCELLED → stale file from a crash during cleanup → delete it.
      - WAITING / FETCHING → live watcher was interrupted → re-create the
        in-memory WATCHERS entry and restart the background polling loop.

    Shutdown: nothing — the state file intentionally persists so the next
    boot's startup hook can find and resume it.
    """
    if state_exists():
        state = read_state()
        if state:
            watcher_id = state.get("watcher_id", "<unknown>")
            status     = state.get("status", "")

            if status in ("DONE", "CANCELLED"):
                # Leftover from a crash during cleanup — remove it.
                delete_state()
                print(f"[lifespan] Stale state file (status={status}) removed.")

            elif status in ("WAITING", "FETCHING"):
                # Active watcher was interrupted — resume it.
                print(f"[lifespan] Resuming watcher {watcher_id} (status={status})…")
                queue: asyncio.Queue = asyncio.Queue()
                WATCHERS[watcher_id] = {
                    "queue":     queue,
                    "cancelled": False,
                }
                # run_watcher_loop is imported lazily here to avoid a
                # circular-import at module load time (it lives in a future
                # phase file that imports from main.py).
                try:
                    from backend.watcher_loop import run_watcher_loop  # noqa: PLC0415
                    asyncio.create_task(run_watcher_loop(watcher_id))
                except ImportError:
                    print("[lifespan] watcher_loop not yet implemented — skipping resume.")

    yield  # ← application runs here
    # (no shutdown logic needed)


app = FastAPI(title="SGBAU Results API", version="1.0.0", lifespan=lifespan)

# ── CORS ───────────────────────────────────────────────────────────────────────
# In production set ALLOWED_ORIGIN to your GitHub Pages URL on Render's dashboard.
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── In-memory job store ────────────────────────────────────────────────────────
# Schema: { job_id: { "queue": asyncio.Queue, "results": [], "done": bool, "error": str|None } }
# Jobs live until the free-tier dyno restarts — acceptable for this use case.
JOBS: dict = {}

# ── In-memory watcher store (Phase 3 §3.5) ────────────────────────────────────
# Schema: { watcher_id (str): { "queue": asyncio.Queue, "cancelled": bool } }
# Populated by POST /api/watch/start and by the lifespan startup resume hook.
# Persisted state lives in backend/watcher_state.json (see backend/watcher.py).
WATCHERS: dict = {}


# ── Helper: approximate total roll count from alphanumeric roll strings ────────

def _count_rolls(departments) -> int:
    """
    Estimate total roll numbers across all departments.
    Strips the alphabetic prefix and counts the numeric range.
    Used only for the progress percentage in the UI — SSE is the ground truth.
    """
    import re
    total = 0
    for d in departments:
        m_s = re.match(r'^(.*?)(\d+)$', d.start_roll)
        m_e = re.match(r'^(.*?)(\d+)$', d.end_roll)
        if m_s and m_e:
            s, e = int(m_s.group(2)), int(m_e.group(2))
            total += abs(e - s) + 1
    return total


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Liveness check — also used by UptimeRobot to keep the free dyno awake."""
    return {"status": "ok"}


@app.post("/api/fetch-results", response_model=FetchResponse, status_code=202)
async def fetch_results(req: FetchRequest, background_tasks: BackgroundTasks):
    """
    Accept a scrape request. Immediately return a job_id (202 Accepted).
    The client then connects to GET /api/progress/{job_id} for SSE updates.
    """
    job_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    JOBS[job_id] = {
        "queue":   queue,
        "results": [],
        "reports": {},          # dept_name -> class_report dict (populated on done)
        "done":    False,
        "error":   None,
    }

    background_tasks.add_task(run_scrape_job, job_id, req)

    return FetchResponse(
        job_id=job_id,
        departments=[d.name for d in req.departments],
        total_rolls=_count_rolls(req.departments),
        message=(
            f"Job {job_id} started. "
            "Connect to /api/progress/{job_id} for live updates."
        ),
    )


@app.get("/api/progress/{job_id}")
async def progress_stream(job_id: str):
    """
    SSE endpoint. Streams JSON events until the scrape job finishes.

    Event shapes:
      { "type": "result", "dept", "roll", "name", "result", "sgpa", "status", "count" }
      { "type": "done",   "summary": [...] }
      { "type": "error",  "message": "..." }
      { "type": "timeout" }           ← if no event arrives within 60 s
    """
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator() -> AsyncGenerator:
        job = JOBS[job_id]
        while True:
            try:
                event = await asyncio.wait_for(job["queue"].get(), timeout=60.0)
            except asyncio.TimeoutError:
                yield {"data": json.dumps({"type": "timeout"})}
                break

            yield {"data": json.dumps(event)}

            if event.get("type") in ("done", "error"):
                break

    return EventSourceResponse(event_generator())


@app.get("/api/download/{job_id}")
async def download_csv(job_id: str):
    """
    Return all collected results for a finished job as a downloadable CSV.
    Includes per-department class report appended after the data rows.
    The client calls this after receiving the 'done' SSE event.
    """
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    all_results = JOBS[job_id].get("results", [])
    if not all_results:
        raise HTTPException(status_code=404, detail="No results available yet")

    df = pd.DataFrame(all_results)

    # ── Columns to always exclude (internal/raw metadata) ─────────────────────
    _EXCLUDE = {
        "Status", "Error", "Department", "Roll Number", "PRN",
        "Session", "Message", "Max Marks",
        # Grade-table header names that sometimes bleed into parsed dicts
        "Subject", "Paper", "THEORY", "I.A.", "I.A.(PRAC)", "PRACTICAL",
        "Abbreviation", "Marks Scored", "Grade Point", "Grade", "Remarks", "Credits",
    }

    # ── Fixed columns we always want (in this order) ──────────────────────────
    FIXED = ["Roll No", "Name", "Result", "SGPA", "College"]

    # ── Subject columns: abbreviated names never contain spaces ───────────────
    subj_cols = [
        c for c in df.columns
        if c not in _EXCLUDE
        and c not in set(FIXED)
        and " " not in c
    ]

    # Keep only columns that actually exist in the dataframe
    ordered   = [c for c in FIXED if c in df.columns] + subj_cols
    df_clean  = df[ordered]

    buf = io.StringIO()
    df_clean.to_csv(buf, index=False)

    # ── Append class report(s) after data rows ─────────────────────────────
    reports = JOBS[job_id].get("reports", {})
    if reports:
        buf.write("\n")   # blank line separator between data and report
        for dept_name, rpt in reports.items():
            buf.write(format_class_report(rpt))
            buf.write("\n")

    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="sgbau_results_{job_id[:8]}.csv"'
            )
        },
    )


# ── Background task ────────────────────────────────────────────────────────────

async def run_scrape_job(job_id: str, req: FetchRequest):
    """
    Runs in FastAPI's background task system (same event loop as the app).
    Drives scrape_departments() and funnels every result into the SSE queue.
    """
    job   = JOBS[job_id]
    queue: asyncio.Queue = job["queue"]
    count = 0

    async def progress_callback(dept_name: str, result: dict):
        nonlocal count
        count += 1

        # Flat event dict for the browser
        event = {
            "type":   "result",
            "dept":   dept_name,
            "roll":   result.get("Roll No", ""),
            "name":   result.get("Name", ""),
            "result": result.get("Result", result.get("Status", "")),
            "sgpa":   result.get("SGPA", ""),
            "status": result.get("Status", ""),
            "count":  count,
        }

        # Persist flat row for CSV download (include dept column)
        job["results"].append({**result, "Department": dept_name})

        await queue.put(event)

    try:
        summaries = await scrape_departments(
            departments=req.departments,
            session_val=req.session,
            course_type=req.course_type,
            result_type=req.result_type,
            sem_code=req.sem_code,
            workers=req.workers,
            progress_callback=progress_callback,
        )

        # ── Store class reports for the download endpoint (Phase 4) ────────────
        for s in summaries:
            if "class_report" in s:
                job["reports"][s["name"]] = s["class_report"]

        # ── Strip raw results list before sending over SSE (too large) ────────
        sse_summaries = [
            {
                "name":         s["name"],
                "range":        s["range"],
                "total":        s["total"],
                "passed":       s["passed"],
                "class_report": s.get("class_report", {}),
            }
            for s in summaries
        ]
        await queue.put({"type": "done", "summary": sse_summaries})

    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})

    finally:
        job["done"] = True


# ── Watcher routes (Phases 5 & 6) ─────────────────────────────────────────────

@app.post("/api/watch/verify-pin", response_model=PinVerifyResponse)
async def verify_pin(req: PinVerifyRequest):
    """
    Phase 5.2 — Verify the admin PIN.

    Uses hmac.compare_digest() for constant-time comparison to prevent
    timing attacks. Always returns HTTP 200 (valid: true/false) — never
    401 — so attackers get no signal via status codes.
    """
    configured_pin = os.getenv("WATCHER_PIN", "")
    if not configured_pin:
        import logging
        logging.getLogger(__name__).warning(
            "WATCHER_PIN env variable is not configured."
        )
        return PinVerifyResponse(valid=False)

    match = hmac.compare_digest(
        configured_pin.encode("utf-8"),
        req.pin.encode("utf-8"),
    )
    return PinVerifyResponse(valid=match)


@app.post("/api/watch/start", response_model=WatchStartResponse, status_code=202)
async def watch_start(req: WatchRequest):
    """
    Phase 5.3 — Start a new watcher session.

    1. Rejects duplicate watchers (one at a time).
    2. Writes watcher_state.json with initial WAITING state.
    3. Registers the queue in WATCHERS.
    4. Spawns the background polling loop.
    """
    if state_exists():
        raise HTTPException(
            status_code=409,
            detail="A watcher is already running. Cancel it before starting a new one.",
        )

    watcher_id = str(uuid.uuid4())
    now        = datetime.utcnow()
    now_str    = now.isoformat(timespec="seconds")
    next_str   = (now + timedelta(minutes=req.interval_minutes)).isoformat(timespec="seconds")

    state_dict = {
        "watcher_id":       watcher_id,
        "dept_name":        req.dept_name,
        "start_roll":       req.start_roll,
        "end_roll":         req.end_roll,
        "sentinel_roll":    req.sentinel_roll,
        "interval_minutes": req.interval_minutes,
        "session":          req.session,
        "course_type":      req.course_type,
        "result_type":      req.result_type,
        "sem_code":         req.sem_code,
        "course_cd":        req.course_cd,
        "status":           "WAITING",
        "probe_count":      0,
        "last_probe_time":  None,
        "next_probe_time":  next_str,
        "created_at":       now_str,
        "cancelled":        False,
    }
    write_state(state_dict)

    queue: asyncio.Queue = asyncio.Queue()
    WATCHERS[watcher_id] = {"queue": queue, "cancelled": False}

    asyncio.create_task(run_watcher_loop(watcher_id))

    return WatchStartResponse(
        watcher_id=watcher_id,
        message=f"Watcher started. First probe in {req.interval_minutes} minutes.",
        sentinel_roll=req.sentinel_roll,
        interval_minutes=req.interval_minutes,
    )


@app.get("/api/watch/current", response_model=WatchCurrentResponse)
async def watch_current():
    """
    Phase 5.4 — Report current watcher state.

    Called by watcher.js on page load (after PIN verification) to restore
    the UI if the admin refreshes the page during an active watch session.
    """
    if not state_exists():
        return WatchCurrentResponse(active=False)

    state = read_state()
    if not state:
        return WatchCurrentResponse(active=False)

    return WatchCurrentResponse(
        active=True,
        watcher_id=state.get("watcher_id"),
        dept_name=state.get("dept_name"),
        status=state.get("status"),
        probe_count=state.get("probe_count"),
        sentinel_roll=state.get("sentinel_roll"),
        interval_minutes=state.get("interval_minutes"),
        last_probe_time=state.get("last_probe_time"),
        next_probe_time=state.get("next_probe_time"),
    )


@app.get("/api/watch/status/{watcher_id}")
async def watch_status_stream(watcher_id: str):
    """
    Phase 6 — SSE stream of live watcher events.

    The frontend connects here after starting a watcher. Events are
    pushed by run_watcher_loop() via the shared asyncio.Queue in WATCHERS.

    Timeout: 90 s (longer than the 30-s sleep chunk so the browser stays
    connected through one full sleep iteration). On timeout the browser's
    built-in SSE reconnect logic automatically re-opens the connection.
    """
    if watcher_id not in WATCHERS:
        raise HTTPException(status_code=404, detail="Watcher not found")

    queue: asyncio.Queue = WATCHERS[watcher_id]["queue"]

    async def event_generator() -> AsyncGenerator:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=90.0)
            except asyncio.TimeoutError:
                yield {"data": json.dumps({"type": "timeout"})}
                break

            yield {"data": json.dumps(event)}

            if event.get("type") in ("done", "cancelled", "error"):
                break

    return EventSourceResponse(event_generator())


@app.post("/api/watch/cancel/{watcher_id}")
async def watch_cancel(watcher_id: str):
    """
    Phase 5.5 — Signal the polling loop to stop.

    Sets both the in-memory cancelled flag and writes it to the state
    file. The loop checks both within 30 seconds and exits cleanly.
    """
    if watcher_id not in WATCHERS:
        raise HTTPException(
            status_code=404,
            detail="Watcher not found in memory. The server may have restarted. "
                   "Call /api/watch/current to check state.",
        )

    WATCHERS[watcher_id]["cancelled"] = True
    update_state(cancelled=True)
    await WATCHERS[watcher_id]["queue"].put(
        {"type": "cancelled", "message": "Watcher stopped by admin."}
    )
    return {"message": "Cancel signal sent."}
