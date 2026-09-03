from pydantic import BaseModel
from typing import List, Optional


class DeptRequest(BaseModel):
    name: str          # e.g. "CSE"
    start_roll: str    # e.g. "25BD310527"
    end_roll: str      # e.g. "25BD310927"
    course_cd: str     # e.g. "C000032"


class FetchRequest(BaseModel):
    departments: List[DeptRequest]
    session: str = "SE23"
    course_type: str = "UG"
    result_type: str = "R"
    sem_code: str = "SM03"
    workers: int = 15


class StudentResult(BaseModel):
    roll_no: str
    name: Optional[str] = None
    result: Optional[str] = None   # "PASS", "FAIL", "ATKT", "ABSENT"
    sgpa: Optional[str] = None
    college: Optional[str] = None
    status: str = "OK"             # "OK", "Not Found / Invalid", "Error", "HTTP 4xx"
    subjects: dict = {}            # { "MATHS": "O", "PHY": "A+" }
    error: Optional[str] = None


class DeptSummary(BaseModel):
    name: str
    total: int
    passed: int
    failed: int
    range: str
    results: List[StudentResult]


class FetchResponse(BaseModel):
    job_id: str
    departments: List[str]
    total_rolls: int
    message: str


# ── Watcher models (Phase 2) ──────────────────────────────────────────────────

class WatchRequest(BaseModel):
    dept_name: str          # Human label shown in logs and Telegram, e.g. "CSE"
    start_roll: str         # First roll for batch fetch when result declared
    end_roll: str           # Last roll for batch fetch
    sentinel_roll: str      # The ONE roll probed each cycle
    interval_minutes: int   # Minutes to sleep between probes, e.g. 45
    session: str            # SGBAU session code, e.g. "SE23"
    course_type: str        # "UG" or "PG"
    result_type: str        # "R" / "B" / "RV" / "EV"
    sem_code: str           # Semester code, e.g. "SM03"
    course_cd: str          # Course code from SGBAU, e.g. "C000032"


class WatchStartResponse(BaseModel):
    watcher_id: str         # UUID string
    message: str            # e.g. "Watcher started. First probe in 45 minutes."
    sentinel_roll: str
    interval_minutes: int


class PinVerifyRequest(BaseModel):
    pin: str                # The PIN entered by the admin


class PinVerifyResponse(BaseModel):
    valid: bool             # True if PIN matches WATCHER_PIN env var


class WatchCurrentResponse(BaseModel):
    active: bool                        # False means no state file exists
    watcher_id: Optional[str] = None
    dept_name: Optional[str] = None
    status: Optional[str] = None        # WAITING / FETCHING / DONE / CANCELLED
    probe_count: Optional[int] = None
    sentinel_roll: Optional[str] = None
    interval_minutes: Optional[int] = None
    last_probe_time: Optional[str] = None   # ISO timestamp
    next_probe_time: Optional[str] = None   # ISO timestamp
