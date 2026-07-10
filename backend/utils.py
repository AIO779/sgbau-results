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
