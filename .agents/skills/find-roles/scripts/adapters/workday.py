"""Workday adapter.

POST endpoint: https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs
Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

ats_slug format: "<tenant>/wd<N>/<site>" e.g. "apple/wd1/External"

Paginates by incrementing offset until total is reached. Throttles to 1 req/sec
per tenant.

See SPEC.md §5.2.4.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters.base import USER_AGENT, AdapterError, http_post_json
from scripts.filters import parse_workday_relative
from scripts.model import LeadRecord, dump_leads


def fetch(ats_slug: str, company_slug: str, max_pages: int = 25, page_size: int = 20) -> list[LeadRecord]:
    parts = ats_slug.strip("/").split("/")
    if len(parts) != 3:
        raise AdapterError(
            f"Workday ats_slug must be '<tenant>/wd<N>/<site>'; got: {ats_slug!r}"
        )
    tenant, wd, site = parts
    if not wd.startswith("wd"):
        raise AdapterError(f"Workday second segment must be like 'wd1', 'wd5'; got: {wd!r}")
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    url = f"{host}/wday/cxs/{tenant}/{site}/jobs"
    referer = f"{host}/{site}"

    extra_headers = {
        "Referer": referer,
        "Origin": host,
        "User-Agent": USER_AGENT,
    }

    leads = []
    offset = 0
    for page in range(max_pages):
        body = {"appliedFacets": {}, "limit": page_size, "offset": offset, "searchText": ""}
        data = http_post_json(url, body, extra_headers=extra_headers)
        postings = data.get("jobPostings") or []
        total = int(data.get("total") or 0)
        if not postings:
            break
        for p in postings:
            external_path = p.get("externalPath") or ""
            ats_id_match = re.search(r"_([A-Za-z0-9-]+)$", external_path)
            ats_id = ats_id_match.group(1) if ats_id_match else external_path.split("/")[-1]
            if not ats_id:
                continue
            title = (p.get("title") or "").strip()
            posting_url = f"{host}{external_path}" if external_path.startswith("/") else external_path
            location = (p.get("locationsText") or p.get("bulletFields", [None])[0] or "").strip() if isinstance(p.get("bulletFields"), list) else (p.get("locationsText") or "").strip()
            posted_str = p.get("postedOn") or ""
            posted_at = parse_workday_relative(posted_str)
            leads.append(LeadRecord(
                company_slug=company_slug,
                ats_id=str(ats_id),
                title=title,
                posting_url=posting_url,
                source="workday",
                location=location,
                department="",
                posted_at=posted_at.isoformat() if posted_at else None,
                content_excerpt="",
            ))
        offset += page_size
        if offset >= total:
            break
        time.sleep(1.0)  # throttle per SPEC §5.2.4
    return leads


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: workday.py <ats_slug=tenant/wdN/site> <company_slug>", file=sys.stderr)
        sys.exit(2)
    try:
        leads = fetch(sys.argv[1], sys.argv[2])
        print(dump_leads(leads))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
