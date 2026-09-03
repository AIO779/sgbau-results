"""
utils.py — Pure, stateless helper functions lifted from sgbau_fast_api.py.
No CLI code, no file I/O, no mutable globals.
"""

import re
import sys
from bs4 import BeautifulSoup


def generate_roll_range(start_roll: str, end_roll: str) -> list:
    """
    Generate all roll numbers between start_roll and end_roll (inclusive).
    Handles alphanumeric prefixes like '25BD310527'.
    Raises ValueError on malformed input (web app never calls sys.exit).
    """
    m_start = re.match(r'^(.*?)(\d+)$', start_roll)
    m_end   = re.match(r'^(.*?)(\d+)$', end_roll)

    if not m_start or not m_end:
        raise ValueError(
            f"Could not parse roll numbers: '{start_roll}', '{end_roll}'"
        )

    prefix_s, num_s = m_start.group(1), m_start.group(2)
    prefix_e, num_e = m_end.group(1),   m_end.group(2)

    if prefix_s != prefix_e:
        raise ValueError(
            f"Roll number prefixes don't match: '{prefix_s}' vs '{prefix_e}'"
        )

    start_num, end_num = int(num_s), int(num_e)
    if start_num > end_num:
        start_num, end_num = end_num, start_num

    width = len(num_s)
    return [f"{prefix_s}{str(n).zfill(width)}" for n in range(start_num, end_num + 1)]


def abbreviate(subject: str) -> str:
    """
    Convert a subject name to an abbreviation.
    e.g. "Applied Mathematics" → "AM", "Data Structures & Algorithms" → "DSA"
    """
    name  = re.sub(r'[*/]', ' ', subject)
    words = re.split(r'[\s&]+', name)
    skip  = {
        'and', 'of', 'the', 'in', 'for', 'to', 'a', 'an',
        'or', 'on', 'at', 'by', 'with', 'field', 'project'
    }
    letters = [w[0].upper() for w in words if w and w.lower() not in skip]
    return ''.join(letters)


_GRADE_TABLE_HEADERS = {
    'Subject', 'Paper', 'THEORY', 'I.A.', 'I.A.(PRAC)', 'PRACTICAL',
    'Abbreviation', 'Marks Scored', 'Grade Point', 'Grade', 'Remarks', 'Credits'
}

_FIELD_ALIASES = [
    ('Student Name',  'Name'),
    ('STUDENT NAME',  'Name'),
    ('Stud Name',     'Name'),
    ('S.G.P.A',       'SGPA'),
    ('SGPA.',         'SGPA'),
    ('RESULT',        'Result'),
    ('College & Code','College'),
    ('College Name',  'College'),
]


def parse_result(html: str, roll: str) -> dict:
    """
    Parse the HTML fragment returned by the SGBAU API for a single roll number.
    Returns a flat dict with keys: Roll No, Status, Name, Result, SGPA, College,
    plus abbreviated subject grade columns (e.g. 'AM', 'DS').
    """
    soup   = BeautifulSoup(html, 'lxml')
    record = {'Roll No': roll, 'Status': 'OK'}

    # ── Pass 1: extract key-value pairs from 2-cell and 6-cell rows ──────────
    for row in soup.find_all('tr'):
        cells = row.find_all(['td', 'th'])

        if len(cells) == 6:
            texts = [c.get_text(strip=True) for c in cells]
            for i in range(0, 6, 2):
                key = texts[i].rstrip(':').strip()
                val = texts[i + 1].strip()
                if key and val:
                    record[key] = val

        elif len(cells) >= 3:
            key = cells[0].get_text(strip=True).rstrip(':').strip()
            if key in _GRADE_TABLE_HEADERS:
                continue
            val = cells[2].get_text(strip=True)
            if key and val:
                record[key] = val

        elif len(cells) == 2:
            key = cells[0].get_text(strip=True).rstrip(':').strip()
            val = cells[1].get_text(strip=True)
            if key and val and not val.startswith(':'):
                record[key] = val

    # ── Pass 2: extract subject grades from rowspan rows ─────────────────────
    for row in soup.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if len(cells) < 7:
            continue
        first = cells[0]
        if first.get('rowspan') == '2' and 'text-align:left' in first.get('style', ''):
            subj_name = first.get_text(strip=True)
            grade     = cells[6].get_text(strip=True)
            if subj_name and grade:
                record[abbreviate(subj_name)] = grade

    # ── Pass 3: fallback result detection from full text ─────────────────────
    if 'Result' not in record:
        full_text = soup.get_text(' ', strip=True)
        for keyword in ('PASS', 'FAIL', 'ATKT', 'ABSENT'):
            if re.search(rf'\b{keyword}\b', full_text, re.IGNORECASE):
                record['Result'] = keyword
                break

    # ── Normalise field names ─────────────────────────────────────────────────
    for alias, canonical in _FIELD_ALIASES:
        if alias in record and canonical not in record:
            record[canonical] = record.pop(alias)

    return record


# ── Info fields that are NOT subject grade columns ────────────────────────────
_INFO_FIELDS = {
    'Roll No', 'Name', 'Result', 'SGPA', 'Status', 'Roll Number', 'PRN',
    'College', 'Session', 'Message', 'Error', 'Max Marks', 'Department',
    'Subject', 'Paper', 'THEORY', 'I.A.', 'I.A.(PRAC)', 'PRACTICAL',
    'Abbreviation', 'Marks Scored', 'Grade Point', 'Grade', 'Remarks', 'Credits',
}


def get_subject_cols(results: list) -> list:
    """
    Return subject-grade column names from a list of result dicts.
    Subject columns: not in _INFO_FIELDS, no spaces (they are abbreviations like 'AM', 'DS').
    Preserves insertion order (first row wins for ordering).
    """
    seen = {}
    for row in results:
        for k in row:
            if k not in _INFO_FIELDS and ' ' not in k and k not in seen:
                seen[k] = True
    return list(seen.keys())


def generate_class_report(results: list, subj_cols: list, dept_name: str = '') -> dict:
    """
    Build a structured class-report dict from a list of result dicts.

    Returns
    -------
    {
        "dept":            str,
        "total_students":  int,
        "passed":          int,
        "failed":          int,
        "pass_pct":        float,
        "top5": [
            {"rank": int, "name": str, "roll": str, "sgpa": float},
            ...
        ],
        "subject_stats": [
            {
                "subject":  str,
                "total":    int,
                "passed":   int,
                "failed":   int,
                "pass_pct": float,
                "fail_pct": float,
            },
            ...
        ],
    }
    """
    # Filter to only OK results
    valid = [r for r in results if r.get('Status') == 'OK'] if results and 'Status' in results[0] else list(results)
    total = len(valid)

    report: dict = {
        'dept':           dept_name,
        'total_students': total,
        'passed':         0,
        'failed':         total,
        'pass_pct':       0.0,
        'top5':           [],
        'subject_stats':  [],
    }

    if total == 0:
        return report

    # ── Overall pass / fail ───────────────────────────────────────────────────
    passed = sum(1 for r in valid if str(r.get('Result', '')).upper() == 'PASS')
    report['passed']   = passed
    report['failed']   = total - passed
    report['pass_pct'] = round((passed / total) * 100, 1)

    # ── Top-5 by SGPA ─────────────────────────────────────────────────────────
    def _to_float(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    scored = []
    for r in valid:
        f = _to_float(r.get('SGPA'))
        if f is not None:
            scored.append((f, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    for rank, (sgpa_val, row) in enumerate(scored[:5], 1):
        report['top5'].append({
            'rank': rank,
            'name': row.get('Name', 'Unknown'),
            'roll': row.get('Roll No', ''),
            'sgpa': sgpa_val,
        })

    # ── Subject-wise pass / fail ──────────────────────────────────────────────
    stats = []
    for col in subj_cols:
        col_data = [r[col] for r in valid if r.get(col) is not None and r.get(col) != '']
        tot = len(col_data)
        if tot == 0:
            continue
        failed_cnt = sum(1 for v in col_data if str(v).upper() == 'F')
        passed_cnt = tot - failed_cnt
        stats.append({
            'subject':  col,
            'total':    tot,
            'passed':   passed_cnt,
            'failed':   failed_cnt,
            'pass_pct': round((passed_cnt / tot) * 100, 1),
            'fail_pct': round((failed_cnt / tot) * 100, 1),
        })

    # Sort by fail % descending (worst subjects first — most useful for teachers)
    stats.sort(key=lambda x: x['fail_pct'], reverse=True)
    report['subject_stats'] = stats

    return report


def format_class_report(report: dict) -> str:
    """
    Convert a generate_class_report() dict into a plain-text block
    suitable for appending to a CSV file (mirrors sgbau_fast_api.py output).
    """
    dept_name = report.get('dept', '')
    header    = f'  CLASS REPORT — {dept_name}' if dept_name else '  CLASS REPORT'
    lines     = ['', '=' * 60, header, '=' * 60]

    total  = report['total_students']
    passed = report['passed']
    failed = report['failed']
    pct    = report['pass_pct']

    if total == 0:
        lines.append('  No valid results to generate a report.')
        return '\n'.join(lines)

    lines.extend([
        '',
        f'  Total Students : {total}',
        f'  Passed         : {passed} ({pct:.1f}%)',
        f'  Failed         : {failed} ({100 - pct:.1f}%)',
    ])

    top5 = report.get('top5', [])
    if top5:
        lines.extend(['', '  --- Top 5 Students (by SGPA) ---'])
        for s in top5:
            lines.append(
                f"  {s['rank']}. {s['name']} (Roll: {s['roll']}) — SGPA: {s['sgpa']}"
            )

    subj_stats = report.get('subject_stats', [])
    if subj_stats:
        lines.extend(['', '  --- Subject-wise Results ---'])
        for s in subj_stats:
            lines.append(
                f"  {s['subject']:>6s} : "
                f"Passed {s['passed']}/{s['total']} ({s['pass_pct']:.0f}%)  |  "
                f"Failed {s['failed']}/{s['total']} ({s['fail_pct']:.0f}%)"
            )

    lines.extend(['', '=' * 60])
    return '\n'.join(lines)
