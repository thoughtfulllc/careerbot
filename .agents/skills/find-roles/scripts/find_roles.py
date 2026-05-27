"""Orchestrator: discover open roles across N companies in parallel.

Usage:
    python3 lib/find_roles.py [options]

Reads a JSON array of company specs on stdin OR auto-discovers from
companies/interested/*.md if --auto is passed. Each company spec must be:

    {
      "slug": "anthropic",
      "ats": "greenhouse",
      "ats_slug": "anthropic",
      "careers_url": "https://www.anthropic.com/careers"  # optional, used for custom adapter
    }

Outputs a single JSON object on stdout:

    {
      "leads": [<LeadRecord>, ...],
      "per_company": { "anthropic": {"status": "ok", "count": 12, "raw_count": 394, ...}, ... },
      "summary": { "total_leads": N, "by_confidence": {...}, "by_source": {...} }
    }

See SPEC.md §5.6 (parallelization), §5.5 (freshness), §5.8 (confidence + caps).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Optional

REPO_LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_LIB.parent))  # so `lib.x` imports work

from scripts.adapters import ashby, custom_html, greenhouse, lever, workable, workday
from scripts.adapters.base import AdapterError
from scripts.filters import classify_title, is_fresh, location_matches
from scripts.model import LeadRecord

ADAPTERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workable": workable.fetch,
}


def _fetch_one(company: dict) -> tuple[dict, list[LeadRecord], Optional[str]]:
    """Dispatch one company to the right adapter. Returns (company, leads, error)."""
    slug = company["slug"]
    ats = (company.get("ats") or "").lower()
    ats_slug = company.get("ats_slug")
    careers_url = company.get("careers_url")

    try:
        if ats == "workday":
            if not ats_slug:
                raise AdapterError(f"{slug}: workday needs ats_slug=<tenant>/wdN/<site>")
            leads = workday.fetch(ats_slug, slug)
        elif ats in ADAPTERS:
            if not ats_slug:
                raise AdapterError(f"{slug}: {ats} needs ats_slug")
            leads = ADAPTERS[ats](ats_slug, slug)
        elif ats == "custom" or not ats:
            if not careers_url:
                raise AdapterError(f"{slug}: custom adapter needs careers_url")
            leads = custom_html.fetch(careers_url, slug)
        else:
            raise AdapterError(f"{slug}: unknown ats={ats!r}")
        return (company, leads, None)
    except AdapterError as e:
        return (company, [], str(e))
    except Exception as e:
        return (company, [], f"unexpected: {e}\n{traceback.format_exc()}")


def filter_and_score(
    leads: list[LeadRecord],
    freshness_days: int,
    today=None,
    default_stream: str = "",
) -> list[LeadRecord]:
    """Apply title / location / freshness filters and set match_confidence.

    If `default_stream` is set and the lead has no stream tag, the lead gets that tag.
    This lets the orchestrator tag Stream B leads as 'B' without modifying the adapter.
    """
    kept = []
    for lead in leads:
        # Title
        matched, conf, t_reason = classify_title(lead.title)
        if not matched:
            continue
        # Location
        loc_ok, l_reason = location_matches(lead.location)
        if not loc_ok:
            continue
        # Freshness
        fresh, f_reason = is_fresh(lead.posted_at, cutoff_days=freshness_days, today=today)
        if not fresh:
            continue
        updates = {
            "match_confidence": conf,
            "match_reasons": (
                f"title: {t_reason}",
                f"location: {l_reason}",
                f"freshness: {f_reason}",
            ),
        }
        if default_stream and not lead.stream:
            updates["stream"] = default_stream
        kept.append(dataclasses.replace(lead, **updates))
    return kept


def dedup(leads: list[LeadRecord], known_urls: set[str], known_ats_ids: set[tuple[str, str]]) -> list[LeadRecord]:
    """Drop leads whose URL or (company_slug, ats_id) is already in the dedup set,
    plus drop content-hash duplicates within this batch."""
    seen_content: set[str] = set()
    out = []
    for lead in leads:
        if lead.posting_url in known_urls:
            continue
        if (lead.company_slug, lead.ats_id) in known_ats_ids:
            continue
        # Content-hash dedup within batch
        ch = _content_hash(lead)
        if ch in seen_content:
            continue
        seen_content.add(ch)
        out.append(lead)
    return out


def _content_hash(lead: LeadRecord) -> str:
    norm = re.sub(r"\s+", " ", f"{lead.company_slug}|{lead.title}|{lead.location}").lower().strip()
    return norm


def cap_per_company(leads: list[LeadRecord], max_per_company: int) -> tuple[list[LeadRecord], dict]:
    """Take top-N per company by (confidence, freshness). Returns (kept, dropped_counts_per_co)."""
    if max_per_company <= 0:
        return (leads, {})
    rank = {"high": 0, "medium": 1, "low": 2, "": 3}
    by_co: dict[str, list[LeadRecord]] = {}
    for lead in leads:
        by_co.setdefault(lead.company_slug, []).append(lead)
    kept = []
    dropped_counts: dict[str, int] = {}
    for co, items in by_co.items():
        items.sort(key=lambda l: (rank.get(l.match_confidence, 3), -(_posted_recency(l.posted_at))))
        keep = items[:max_per_company]
        drop = len(items) - len(keep)
        if drop > 0:
            dropped_counts[co] = drop
        kept.extend(keep)
    return (kept, dropped_counts)


def _posted_recency(posted_at: Optional[str]) -> int:
    """Return a sortable int: newer = larger. Unknown = 0."""
    if not posted_at:
        return 0
    try:
        import datetime as dt
        return (dt.date.fromisoformat(posted_at) - dt.date(2000, 1, 1)).days
    except Exception:
        return 0


def recency_tier(posted_at: Optional[str], fresh_days: int, today=None) -> int:
    """Bucket a posting age into a sortable tier.

    0 = fresh (age <= fresh_days, or future-dated due to clock skew)
    1 = normal (fresh_days < age, including very old; the 90d hard filter runs earlier)
    2 = unknown (no posted_at, or unparseable)

    Pass fresh_days=0 to disable the boost (collapses tier 0 into tier 1 for all dated roles).
    """
    if not posted_at:
        return 2
    try:
        import datetime as dt
        posted = dt.date.fromisoformat(posted_at)
    except (ValueError, TypeError):
        return 2
    today = today or __import__("datetime").date.today()
    age = (today - posted).days
    if fresh_days <= 0:
        return 1
    if age <= fresh_days:  # includes future-dated (negative age)
        return 0
    return 1


def load_dedup_set(dedup_paths: list[str]) -> tuple[set[str], set[tuple[str, str]]]:
    """Parse existing application markdown files to collect (url, ats_id) pairs."""
    known_urls: set[str] = set()
    known_ats_ids: set[tuple[str, str]] = set()
    for path_str in dedup_paths:
        path = Path(path_str)
        if not path.exists():
            continue
        for md in path.rglob("*.md"):
            try:
                text = md.read_text()
            except Exception:
                continue
            frontmatter = _extract_frontmatter(text)
            url = frontmatter.get("url")
            ats_id = frontmatter.get("ats_id")
            company = frontmatter.get("company")
            if url:
                known_urls.add(url.strip().strip('"').strip("'"))
            if ats_id and company:
                known_ats_ids.add((company.strip().strip('"').strip("'"), ats_id.strip().strip('"').strip("'")))
    return (known_urls, known_ats_ids)


_FM_LINE = re.compile(r"^([a-zA-Z_]+):\s*(.+?)\s*$")


def _extract_frontmatter(text: str) -> dict:
    """Tiny YAML frontmatter parser — handles only flat key: value lines."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    out: dict[str, str] = {}
    for line in fm.strip().split("\n"):
        m = _FM_LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def load_companies_from_dir(dir_path: str) -> list[dict]:
    """Walk companies/interested/*.md and extract ATS routing info from frontmatter."""
    out = []
    p = Path(dir_path)
    if not p.exists():
        return out
    for md in sorted(p.glob("*.md")):
        if md.name.startswith("."):
            continue
        text = md.read_text()
        fm = _extract_frontmatter(text)
        slug = fm.get("slug") or md.stem
        out.append({
            "slug": slug.strip().strip('"').strip("'"),
            "ats": (fm.get("ats") or "").strip().strip('"').strip("'") or None,
            "ats_slug": (fm.get("ats_slug") or "").strip().strip('"').strip("'") or None,
            "careers_url": (fm.get("careers_url") or "").strip().strip('"').strip("'") or None,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover open roles across companies in parallel.")
    ap.add_argument("--companies-dir", default="companies/interested", help="Auto-load companies from this directory (default).")
    ap.add_argument("--input", help="Read companies as JSON array from this file instead of --companies-dir.")
    ap.add_argument("--freshness-days", type=int, default=90)
    ap.add_argument("--max-per-company", type=int, default=8)
    ap.add_argument("--max-total", type=int, default=200)
    ap.add_argument("--dedup-from", action="append", default=[], help="Repeat; each path is a directory of application .md files to dedup against.")
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = ap.parse_args()

    if args.input:
        companies = json.loads(Path(args.input).read_text())
    else:
        companies = load_companies_from_dir(args.companies_dir)

    if not companies:
        print(json.dumps({"error": "no companies loaded", "leads": [], "per_company": {}, "summary": {}}), file=sys.stdout)
        return 1

    known_urls, known_ats_ids = load_dedup_set(args.dedup_from or [])

    per_company: dict[str, dict] = {}
    all_leads: list[LeadRecord] = []
    errors: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {ex.submit(_fetch_one, c): c for c in companies}
        for fut in concurrent.futures.as_completed(futures):
            company, leads, err = fut.result()
            slug = company["slug"]
            raw_count = len(leads)
            kept = filter_and_score(leads, freshness_days=args.freshness_days, default_stream="B")
            kept = dedup(kept, known_urls, known_ats_ids)
            per_company[slug] = {
                "status": "ok" if err is None else "error",
                "ats": company.get("ats"),
                "raw_count": raw_count,
                "kept_count": len(kept),
                "error": err,
            }
            if err:
                errors.append(f"{slug}: {err}")
            all_leads.extend(kept)

    # Cap per company
    all_leads, dropped_counts = cap_per_company(all_leads, args.max_per_company)
    for co, n in dropped_counts.items():
        per_company.setdefault(co, {})["dropped_over_cap"] = n

    # Global sort + cap
    rank = {"high": 0, "medium": 1, "low": 2, "": 3}
    all_leads.sort(key=lambda l: (rank.get(l.match_confidence, 3), -(_posted_recency(l.posted_at))))
    if args.max_total > 0:
        all_leads = all_leads[: args.max_total]

    # Summary
    summary = {
        "companies_scanned": len(companies),
        "total_leads": len(all_leads),
        "by_confidence": _count_by(all_leads, "match_confidence"),
        "by_source": _count_by(all_leads, "source"),
        "errors": errors,
    }

    output = {
        "leads": [dataclasses.asdict(l) for l in all_leads],
        "per_company": per_company,
        "summary": summary,
    }
    # Strip 'raw' field
    for l in output["leads"]:
        l.pop("raw", None)

    indent = 2 if args.pretty else None
    print(json.dumps(output, ensure_ascii=False, indent=indent))
    return 0


def _count_by(leads: list[LeadRecord], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for l in leads:
        v = getattr(l, field) or "(none)"
        out[v] = out.get(v, 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
