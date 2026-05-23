"""Lever adapter.

Endpoint: https://api.lever.co/v0/postings/<ats_slug>?mode=json
Returns all active postings in one call. Free. No auth.

See SPEC.md §5.2.2.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters.base import AdapterError, http_get_json, truncate_excerpt
from scripts.filters import parse_epoch_ms
from scripts.model import LeadRecord, dump_leads


def fetch(ats_slug: str, company_slug: str) -> list[LeadRecord]:
    url = f"https://api.lever.co/v0/postings/{ats_slug}?mode=json"
    data = http_get_json(url)
    # Lever returns a bare list (not wrapped in {jobs: [...]})
    postings = data if isinstance(data, list) else (data.get("postings") or [])
    leads = []
    for p in postings:
        ats_id = str(p.get("id") or "")
        if not ats_id:
            continue
        title = (p.get("text") or "").strip()
        categories = p.get("categories") or {}
        location = (categories.get("location") or "").strip()
        department = (categories.get("department") or categories.get("team") or "").strip()
        posting_url = p.get("hostedUrl") or f"https://jobs.lever.co/{ats_slug}/{ats_id}"
        created_at = parse_epoch_ms(p.get("createdAt"))
        # Lever description is in `description` (HTML) or `descriptionPlain`
        excerpt_src = p.get("descriptionPlain") or re.sub(r"<[^>]+>", " ", p.get("description") or "")
        # Try Lever's structured salary range first (set by some boards via `salary`)
        comp_min = comp_max = None
        salary = p.get("salaryRange") or {}
        if salary:
            comp_min = salary.get("min")
            comp_max = salary.get("max")
        leads.append(LeadRecord(
            company_slug=company_slug,
            ats_id=ats_id,
            title=title,
            posting_url=posting_url,
            source="lever",
            location=location,
            department=department,
            posted_at=created_at.isoformat() if created_at else None,
            comp_min=comp_min,
            comp_max=comp_max,
            content_excerpt=truncate_excerpt(excerpt_src),
        ))
    return leads


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: lever.py <ats_slug> <company_slug>", file=sys.stderr)
        sys.exit(2)
    try:
        leads = fetch(sys.argv[1], sys.argv[2])
        print(dump_leads(leads))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
