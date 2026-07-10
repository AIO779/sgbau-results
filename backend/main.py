"""
main.py — FastAPI application.
Routes: POST /api/fetch-results, GET /api/progress/{job_id},
        GET /api/download/{job_id}, GET /api/health
"""

import asyncio
import io
import json
import os
import uuid
from typing import AsyncGenerator

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from backend.models import FetchRequest, FetchResponse
from backend.scraper import scrape_departments

app = FastAPI(title="SGBAU Results API", version="1.0.0")

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
        "Status", "Error", "Department", "Result", "Roll Number", "PRN",
        "Session", "Message", "Max Marks",
        # Grade-table header names that sometimes bleed into parsed dicts
        "Subject", "Paper", "THEORY", "I.A.", "I.A.(PRAC)", "PRACTICAL",
        "Abbreviation", "Marks Scored", "Grade Point", "Grade", "Remarks", "Credits",
    }

    # ── Fixed columns we always want (in this order) ──────────────────────────
    FIXED = ["Roll No", "Name", "SGPA", "College"]

    # ── Subject columns: abbreviated names never contain spaces ───────────────
    subj_cols = [
        c for c in df.columns
        if c not in _EXCLUDE
        and c not in set(FIXED)
        and " " not in c
    ]

    # Keep only columns that actually exist in the dataframe
    ordered = [c for c in FIXED if c in df.columns] + subj_cols
    df_clean = df[ordered]

    buf = io.StringIO()
    df_clean.to_csv(buf, index=False)
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
        await queue.put({"type": "done", "summary": summaries})

    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})

    finally:
        job["done"] = True
