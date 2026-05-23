"""Stream A: title-wide ATS search enrichment.

The skill prompt issues 16 WebSearch calls (4 hosts × 4 title groups) and
collects URL hits into a JSON file shaped like:

    [{"url": "https://boards.greenhouse.io/anthropic/jobs/5104689008",
      "title": "Senior Product Designer",
      "description": "..."}, ...]

This script parses each URL to extract (ats, ats_slug, ats_id), groups by
(ats, ats_slug), calls the corresponding ATS adapter once per slug to pull
all that slug's roles, then filters down to roles whose ats_id appeared in
the original hits. The result is a list of full LeadRecord objects.

Why two-pass: search snippets are unstructured. The adapter call gives us
canonical title / location / posted_at / comp data we can filter against
existing rule libraries.

See SPEC.md §13.1.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters import ashby, greenhouse, lever
from scripts.adapters.base import AdapterError
from scripts.model import LeadRecord


ADAPTERS = {
    "greenhouse": greenhouse.fetch,
    "ashby": ashby.fetch,
    "lever": lever.fetch,
}


def parse_url(url: str) -> Optional[tuple[str, str, str]]:
    """Return (ats, ats_slug, ats_id) or None if not a recognized ATS URL."""
    if not url:
        return None
    p = urlparse(url)
    host = p.netloc.lower()
    parts = [x for x in p.path.split("/") if x]

    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        # /<slug>/jobs/<id> or /embed/job_app?token=<id>
        if len(parts) >= 3 and parts[1] == "jobs":
            return ("greenhouse", parts[0], parts[2])
        # Embed link — extract token from query string
        if parts and parts[0] == "embed":
            m = re.search(r"token=([0-9]+)", p.query)
            if m:
                return ("greenhouse", _greenhouse_slug_from_referrer(url), m.group(1))
        return None

    if host == "jobs.lever.co":
        # /<slug>/<id> or /<slug>/<id>/apply
        if len(parts) >= 2:
            return ("lever", parts[0], parts[1])
        return None

    if host == "jobs.ashbyhq.com":
        # /<slug>/<id> or /<slug>/<id>/application
        if len(parts) >= 2:
            return ("ashby", parts[0], parts[1])
        return None

    return None


def _greenhouse_slug_from_referrer(url: str) -> str:
    """Embed links don't carry slug in the URL. Fallback: return empty."""
    return ""


def enrich(hits: list[dict]) -> list[LeadRecord]:
    """Parse hits, group by (ats, slug), call adapters, filter to matching ats_ids."""
    by_slug: dict[tuple[str, str], set[str]] = {}
    for hit in hits:
        parsed = parse_url(hit.get("url") or "")
        if not parsed:
            continue
        ats, ats_slug, ats_id = parsed
        if not ats_slug or not ats_id:
            continue
        key = (ats, ats_slug)
        by_slug.setdefault(key, set()).add(ats_id)

    leads: list[LeadRecord] = []

    def fetch_slug(key: tuple[str, str]) -> list[LeadRecord]:
        ats, ats_slug = key
        try:
            all_leads = ADAPTERS[ats](ats_slug, ats_slug)  # use ats_slug as company_slug temporarily
        except AdapterError:
            return []
        wanted = by_slug[key]
        return [l for l in all_leads if l.ats_id in wanted]

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for batch in ex.map(fetch_slug, list(by_slug.keys())):
            leads.extend(batch)
    # Tag every lead with stream='A' for downstream reporting
    return [dataclasses.replace(l, stream="A") for l in leads]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="JSON file with list of {url, title, description}. Default: stdin.")
    args = ap.parse_args()

    if args.input:
        hits = json.loads(Path(args.input).read_text())
    else:
        hits = json.loads(sys.stdin.read())

    if not isinstance(hits, list):
        # Allow a wrapper like {"hits": [...]}
        hits = hits.get("hits") or hits.get("urls") or []

    leads = enrich(hits)
    out = [dataclasses.asdict(l) for l in leads]
    for o in out:
        o.pop("raw", None)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
