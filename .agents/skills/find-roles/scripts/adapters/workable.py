"""Workable adapter.

Endpoint: https://apply.workable.com/api/v1/widget/accounts/<ats_slug>?details=true
Returns all active postings in one call. Free. No auth.

See SPEC.md §5.2.5.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters.base import AdapterError, http_get_json, truncate_excerpt
from scripts.filters import parse_iso
from scripts.model import LeadRecord, dump_leads


def fetch(ats_slug: str, company_slug: str) -> list[LeadRecord]:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{ats_slug}?details=true"
    data = http_get_json(url)
    jobs = data.get("jobs") or []
    leads = []
    for j in jobs:
        ats_id = str(j.get("shortcode") or j.get("id") or "")
        if not ats_id:
            continue
        title = (j.get("title") or "").strip()
        # Posting URL: workable uses /j/<shortcode>
        posting_url = j.get("application_url") or j.get("url") or f"https://apply.workable.com/{ats_slug}/j/{ats_id}/"
        loc_obj = j.get("location") or {}
        loc_parts = [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")]
        location = ", ".join([p for p in loc_parts if p])
        if loc_obj.get("workplace_type"):
            location = f"{loc_obj.get('workplace_type')}: {location}".strip(": ")
        department = (j.get("department") or "").strip()
        published = parse_iso(j.get("published_on") or j.get("created_at"))
        # Description
        descr = j.get("description") or j.get("requirements") or ""
        descr_text = re.sub(r"<[^>]+>", " ", descr)
        leads.append(LeadRecord(
            company_slug=company_slug,
            ats_id=ats_id,
            title=title,
            posting_url=posting_url,
            source="workable",
            location=location,
            department=department,
            posted_at=published.isoformat() if published else None,
            content_excerpt=truncate_excerpt(descr_text),
        ))
    return leads


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: workable.py <ats_slug> <company_slug>", file=sys.stderr)
        sys.exit(2)
    try:
        leads = fetch(sys.argv[1], sys.argv[2])
        print(dump_leads(leads))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
