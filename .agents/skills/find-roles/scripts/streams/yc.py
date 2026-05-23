"""Stream C: YC firehose.

Fetches yc-oss.github.io/api/companies/all.json, filters by:
- status: Active
- isHiring: true
- batch in {W24, S24, F24, W25, S25, F25, X25, W26} (last ~2 years)
- industry tags loosely matching preferences.md.industries_want

For each surviving company, tries to resolve its ATS via slug-probing (reuses
backfill_ats_metadata.probe_by_slug). Calls the corresponding adapter to pull
roles. Outputs LeadRecord JSON.

Caps at top N candidates (default 40) sorted by team_size (proxy for "has
budget to hire").

See SPEC.md §13.3.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters import ashby, greenhouse, lever, workable
from scripts.adapters.base import USER_AGENT, AdapterError
from scripts.backfill_ats_metadata import probe_by_slug
from scripts.model import LeadRecord


YC_API_URL = "https://yc-oss.github.io/api/companies/all.json"

RECENT_BATCHES = {
    "W24", "Winter 2024",
    "S24", "Summer 2024",
    "F24", "Fall 2024",
    "W25", "Winter 2025",
    "S25", "Summer 2025",
    "Spring 2025",
    "F25", "Fall 2025",
    "X25", "X 2025",
    "W26", "Winter 2026",
}

ADAPTERS = {
    "greenhouse": greenhouse.fetch,
    "ashby": ashby.fetch,
    "lever": lever.fetch,
    "workable": workable.fetch,
}

# Industry tag keywords — soft filter. Any match counts. Lowercased.
DEFAULT_INDUSTRY_KEYWORDS = [
    "ai", "ml", "machine learning", "agent",
    "developer", "dev tool", "devtool", "devops", "infrastructure",
    "design", "creator", "creative",
    "health", "bio", "medical", "biotech",
    "consumer", "productivity",
]


def fetch_yc_directory() -> list[dict]:
    req = urllib.request.Request(YC_API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def candidate_score(company: dict, industry_kws: list[str]) -> int:
    """Score for ranking. Higher = better."""
    blob = " ".join([
        company.get("one_liner") or "",
        company.get("long_description") or "",
        company.get("subindustry") or "",
        " ".join(company.get("industries") or []),
        " ".join(company.get("tags") or []),
    ]).lower()
    score = 0
    for kw in industry_kws:
        if kw in blob:
            score += 1
    # Team size as tiebreaker (small companies more likely to hire flexibly)
    ts = company.get("team_size") or 0
    if isinstance(ts, int):
        # Sweet spot 10-80 for designer roles
        if 10 <= ts <= 80:
            score += 2
        elif 5 <= ts < 10:
            score += 1
        elif 80 < ts <= 200:
            score += 1
    return score


def filter_yc(companies: list[dict], industry_kws: list[str], known_slugs: set[str]) -> list[dict]:
    out = []
    for c in companies:
        if c.get("status") != "Active":
            continue
        if not c.get("isHiring"):
            continue
        if (c.get("batch") or "") not in RECENT_BATCHES:
            continue
        slug = c.get("slug")
        if not slug or slug in known_slugs:
            continue
        s = candidate_score(c, industry_kws)
        if s <= 0:
            continue
        c["_score"] = s
        out.append(c)
    out.sort(key=lambda c: c["_score"], reverse=True)
    return out


def load_known_slugs(companies_root: str) -> set[str]:
    known = set()
    root = Path(companies_root)
    if not root.exists():
        return known
    for status in ["interested", "in-review", "not-interested"]:
        d = root / status
        if d.exists():
            for md in d.glob("*.md"):
                known.add(md.stem)
    return known


def resolve_and_fetch(company: dict) -> list[LeadRecord]:
    """Resolve ATS for one YC company and pull its roles."""
    slug = company["slug"]
    ats, ats_slug, _ = probe_by_slug(slug)
    if not ats or ats not in ADAPTERS:
        return []
    try:
        leads = ADAPTERS[ats](ats_slug, slug)
    except AdapterError:
        return []
    name = company.get("name") or slug
    return [dataclasses.replace(l, stream="C", company_name=name) for l in leads]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies-root", default="companies", help="Root of companies/ tree (for dedup of known slugs)")
    ap.add_argument("--max-candidates", type=int, default=40)
    ap.add_argument("--concurrency", type=int, default=12)
    args = ap.parse_args()

    companies = fetch_yc_directory()
    known = load_known_slugs(args.companies_root)
    candidates = filter_yc(companies, DEFAULT_INDUSTRY_KEYWORDS, known)[: args.max_candidates]

    all_leads: list[LeadRecord] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for leads in ex.map(resolve_and_fetch, candidates):
            all_leads.extend(leads)

    out = [dataclasses.asdict(l) for l in all_leads]
    for o in out:
        o.pop("raw", None)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(
        f"# yc.py: {len(candidates)} candidates probed, "
        f"{sum(1 for l in all_leads)} total roles found, "
        f"{len({l.company_slug for l in all_leads})} unique companies",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
