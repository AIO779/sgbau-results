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
    workers: int = 50


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
