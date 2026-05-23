"""Ashby adapter.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/<ats_slug>?includeCompensation=true
Returns all active postings in one call. Free. No auth.

See SPEC.md §5.2.3.
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
    url = f"https://api.ashbyhq.com/posting-api/job-board/{ats_slug}?includeCompensation=true"
    data = http_get_json(url)
    jobs = data.get("jobs") or []
    leads = []
    for j in jobs:
        ats_id = str(j.get("id") or "")
        if not ats_id:
            continue
        title = (j.get("title") or "").strip()
        posting_url = j.get("jobUrl") or f"https://jobs.ashbyhq.com/{ats_slug}/{ats_id}"
        # Location: primary + secondary
        primary_loc = (j.get("locationName") or "").strip()
        secondaries = j.get("secondaryLocations") or []
        all_locs = [primary_loc] + [s.get("locationName", "") for s in secondaries if s.get("locationName")]
        location = ", ".join([l for l in all_locs if l])
        department = (j.get("departmentName") or j.get("teamName") or "").strip()
        published = parse_iso(j.get("publishedDate") or j.get("publishedAt"))
        # Compensation
        comp_min = comp_max = None
        comp = j.get("compensation") or {}
        tiers = comp.get("compensationTiers") or comp.get("tiers") or []
        if tiers:
            # Take the first tier's range
            first = tiers[0] or {}
            comp_min = first.get("minValue") or first.get("min")
            comp_max = first.get("maxValue") or first.get("max")
        # Excerpt
        descr = j.get("descriptionPlain") or re.sub(r"<[^>]+>", " ", j.get("descriptionHtml") or "")
        leads.append(LeadRecord(
            company_slug=company_slug,
            ats_id=ats_id,
            title=title,
            posting_url=posting_url,
            source="ashby",
            location=location,
            department=department,
            posted_at=published.isoformat() if published else None,
            comp_min=int(comp_min) if isinstance(comp_min, (int, float)) else None,
            comp_max=int(comp_max) if isinstance(comp_max, (int, float)) else None,
            content_excerpt=truncate_excerpt(descr),
        ))
    return leads


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ashby.py <ats_slug> <company_slug>", file=sys.stderr)
        sys.exit(2)
    try:
        leads = fetch(sys.argv[1], sys.argv[2])
        print(dump_leads(leads))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
