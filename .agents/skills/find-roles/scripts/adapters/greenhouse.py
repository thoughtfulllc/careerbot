"""Greenhouse adapter.

Endpoint: https://boards-api.greenhouse.io/v1/boards/<ats_slug>/jobs?content=true
Returns all active jobs in one call. Free. No auth.

See SPEC.md §5.2.1.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

# Allow running as a script: python3 lib/adapters/greenhouse.py <slug>
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters.base import AdapterError, http_get_json, truncate_excerpt
from scripts.filters import parse_iso
from scripts.model import LeadRecord, dump_leads


def fetch(ats_slug: str, company_slug: str, include_content: bool = True) -> list[LeadRecord]:
    suffix = "?content=true" if include_content else ""
    url = f"https://boards-api.greenhouse.io/v1/boards/{ats_slug}/jobs{suffix}"
    data = http_get_json(url)
    jobs = data.get("jobs", []) or []
    leads = []
    for j in jobs:
        ats_id = str(j.get("id") or "")
        if not ats_id:
            continue
        title = (j.get("title") or "").strip()
        posting_url = j.get("absolute_url") or f"https://job-boards.greenhouse.io/{ats_slug}/jobs/{ats_id}"
        location = ((j.get("location") or {}).get("name") or "").strip()
        departments = j.get("departments") or []
        department = (departments[0].get("name") if departments else "") or ""
        updated_at = parse_iso(j.get("updated_at"))
        # Greenhouse returns content as HTML-entity-encoded HTML in `content`.
        # Decode entities, then strip tags.
        content_raw = j.get("content") or ""
        content_text = re.sub(r"<[^>]+>", " ", html.unescape(content_raw))
        # Greenhouse sometimes includes pay range in metadata
        comp_min, comp_max = _extract_comp(content_text)
        leads.append(LeadRecord(
            company_slug=company_slug,
            ats_id=ats_id,
            title=title,
            posting_url=posting_url,
            source="greenhouse",
            location=location,
            department=department,
            posted_at=updated_at.isoformat() if updated_at else None,
            comp_min=comp_min,
            comp_max=comp_max,
            content_excerpt=truncate_excerpt(content_text),
        ))
    return leads


_COMP_RANGE = re.compile(
    r"\$\s*(\d{2,3}(?:,\d{3})?(?:\s*[KkMm])?)\s*[-–to]+\s*\$?\s*(\d{2,3}(?:,\d{3})?(?:\s*[KkMm])?)",
)


def _extract_comp(text: str) -> tuple[int | None, int | None]:
    """Best-effort comp-range extraction from posting text."""
    if not text:
        return (None, None)
    m = _COMP_RANGE.search(text)
    if not m:
        return (None, None)
    def to_int(s: str) -> int | None:
        s = s.strip().replace(",", "")
        mult = 1
        if s.lower().endswith("k"):
            mult = 1_000
            s = s[:-1].strip()
        elif s.lower().endswith("m"):
            mult = 1_000_000
            s = s[:-1].strip()
        try:
            return int(float(s) * mult)
        except ValueError:
            return None
    return (to_int(m.group(1)), to_int(m.group(2)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: greenhouse.py <ats_slug> <company_slug>", file=sys.stderr)
        sys.exit(2)
    try:
        leads = fetch(sys.argv[1], sys.argv[2])
        print(dump_leads(leads))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
