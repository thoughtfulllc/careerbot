"""Unified discovery pipeline — runs all three streams + route + finalize in-process.

Replaces the v2 /tmp/ JSON pipe between six separate script invocations with
one in-process pipeline that takes two input files (from the skill prompt's
WebSearch / LLM-judgment work) and emits final leads + stubs.

Invoked twice per /find-roles run:

    # Phase 1: discover — runs streams A/B/C in parallel, dedups, routes
    python3 scripts/pipeline.py discover \
        --stream-a-hits .cache/find-roles/stream-a-hits.json \
        --companies-root companies \
        --dedup-from applications/in-review --dedup-from applications/applied [...] \
        --workdir .cache/find-roles

    # (skill prompt does industry check on unknown slugs, writes industry.json)

    # Phase 2: finalize — applies industry verdicts, sorts, caps, writes stubs
    python3 scripts/pipeline.py finalize \
        --industry .cache/find-roles/industry.json \
        --companies-root companies \
        --write-stubs \
        --workdir .cache/find-roles

The per-component CLIs (find_roles.py, streams/yc.py, streams/title_search.py,
auto_stub.py) remain for per-stream debugging. ``enrich_leads.py`` is now a
library-only module — its routing/finalize logic lives here in ``pipeline.py``.

See SPEC.md Part 2 + the v2 architecture diagram.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import sys
from pathlib import Path
from typing import Optional

REPO_LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_LIB.parent))

from scripts import auto_stub, enrich_leads, find_roles
from scripts.model import LeadRecord, dump_leads
from scripts.streams import title_search, yc


# ---------- Discovery (Phase 1) ----------

def run_stream_a(hits_path: Path) -> list[LeadRecord]:
    if not hits_path.exists():
        return []
    hits = json.loads(hits_path.read_text())
    if isinstance(hits, dict):
        hits = hits.get("hits") or hits.get("urls") or []
    return title_search.enrich(hits)


def run_stream_b(companies_dir: str, freshness_days: int) -> list[LeadRecord]:
    """Stream B is the per-company sweep of companies/interested/ ATS boards."""
    companies = find_roles.load_companies_from_dir(companies_dir)
    if not companies:
        return []
    all_leads: list[LeadRecord] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for company, leads, err in ex.map(find_roles._fetch_one, companies):
            if err:
                continue
            all_leads.extend(leads)
    return find_roles.filter_and_score(all_leads, freshness_days=freshness_days, default_stream="B")


def run_stream_c(companies_root: str, max_candidates: int) -> list[LeadRecord]:
    directory = yc.fetch_yc_directory()
    known = yc.load_known_slugs(companies_root)
    candidates = yc.filter_yc(directory, yc.DEFAULT_INDUSTRY_KEYWORDS, known)[:max_candidates]
    all_leads: list[LeadRecord] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for leads in ex.map(yc.resolve_and_fetch, candidates):
            all_leads.extend(leads)
    return all_leads


def discover(
    stream_a_hits_path: Path,
    companies_dir: str,
    companies_root: str,
    dedup_paths: list[str],
    freshness_days: int,
    yc_max_candidates: int,
) -> tuple[list[LeadRecord], list[str]]:
    """Run streams A/B/C in parallel, merge, filter, dedup, route.

    Returns (routed_leads, unknown_slugs).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        fut_a = ex.submit(run_stream_a, stream_a_hits_path)
        fut_b = ex.submit(run_stream_b, companies_dir, freshness_days)
        fut_c = ex.submit(run_stream_c, companies_root, yc_max_candidates)
        stream_a = fut_a.result()
        stream_b = fut_b.result()
        stream_c = fut_c.result()

    # Merge + filter + reverse-map + dedup + route
    merged = stream_a + stream_b + stream_c
    filtered = find_roles.filter_and_score(merged, freshness_days=freshness_days)

    ats_map = enrich_leads.build_ats_to_slug_map(companies_root)
    filtered = [
        dataclasses.replace(l, company_slug=ats_map[(l.source.lower(), l.company_slug.lower())])
        if (l.source.lower(), l.company_slug.lower()) in ats_map
        else l
        for l in filtered
    ]

    known_urls, known_ats_ids = find_roles.load_dedup_set(dedup_paths)
    seen_content: set[str] = set()
    deduped: list[LeadRecord] = []
    for l in filtered:
        if l.posting_url in known_urls:
            continue
        if (l.company_slug, l.ats_id) in known_ats_ids:
            continue
        ch = find_roles._content_hash(l)
        if ch in seen_content:
            continue
        seen_content.add(ch)
        deduped.append(l)

    routed: list[LeadRecord] = []
    for l in deduped:
        status = enrich_leads.status_for_slug(l.company_slug, companies_root)
        if status == "not-interested":
            continue
        routed.append(dataclasses.replace(l, priority=status))

    unknown_slugs = sorted({l.company_slug for l in routed if l.priority == "new-discovery"})

    return (
        routed,
        unknown_slugs,
    )


# ---------- Finalize (Phase 2) ----------

def finalize(
    routed: list[LeadRecord],
    industry: dict,
    max_total: int,
    known_good_cap: int,
    in_review_cap: int,
    new_discovery_cap: int,
    companies_root: str = "companies",
    preferences_path: str = "context/preferences.md",
) -> tuple[list[LeadRecord], list[dict], list[dict]]:
    """Apply industry filter, sort, cap with cascade. Returns (final, stubs, drops)."""
    # Soft-score industries_want (used as secondary sort key — not a filter)
    industries_want = enrich_leads.load_industries_want(preferences_path)

    surviving: list[LeadRecord] = []
    industry_drops: list[dict] = []
    for l in routed:
        updates: dict = {}
        if l.priority == "new-discovery":
            verdict = industry.get(l.company_slug)
            if verdict:
                updates["industry_check"] = verdict.get("status", "")
                updates["industry_check_reason"] = verdict.get("reason", "")
                if not l.company_name:
                    updates["company_name"] = verdict.get("company_name") or l.company_slug
                if verdict.get("status") == "blocked":
                    industry_drops.append({
                        "slug": l.company_slug,
                        "title": l.title,
                        "reason": verdict.get("reason"),
                        "keywords": verdict.get("matched_keywords"),
                    })
                    continue
            else:
                updates["industry_check"] = "skipped"
                updates["industry_check_reason"] = "no industry check verdict provided"
        else:
            updates["industry_check"] = "n/a"
        # Score industries_want as a soft sort signal (not a filter)
        updates["industry_match"] = enrich_leads.score_industry_match(l, industries_want, companies_root)
        surviving.append(dataclasses.replace(l, **updates))

    # Sort: priority → industry_match (higher first) → confidence → freshness (newer first)
    surviving.sort(
        key=lambda l: (
            enrich_leads.PRIORITY_RANK.get(l.priority, 3),
            -l.industry_match,  # higher industry_match floats up
            enrich_leads.CONFIDENCE_RANK.get(l.match_confidence, 3),
            -find_roles._posted_recency(l.posted_at),
        )
    )

    # Per-priority cap with downward cascade
    caps = {"known-good": known_good_cap, "in-review": in_review_cap, "new-discovery": new_discovery_cap}
    bucket_order = ["known-good", "in-review", "new-discovery"]
    by_bucket: dict[str, list[LeadRecord]] = {b: [] for b in bucket_order}
    for l in surviving:
        by_bucket.setdefault(l.priority, []).append(l)

    final: list[LeadRecord] = []
    carry = 0
    for b in bucket_order:
        cap = caps.get(b, 0) + carry
        take = by_bucket.get(b, [])[:cap]
        final.extend(take)
        carry = max(0, cap - len(take))

    final = final[:max_total]

    # Build stub-to-create list
    stub_dict: dict[str, dict] = {}
    for l in final:
        if l.priority != "new-discovery":
            continue
        if l.company_slug in stub_dict:
            continue
        stub_dict[l.company_slug] = {
            "slug": l.company_slug,
            "name": l.company_name or enrich_leads._title_case_slug(l.company_slug),
            "ats": l.source if l.source in {"greenhouse", "lever", "ashby", "workable", "workday"} else "custom",
            "ats_slug": l.company_slug if l.source in {"greenhouse", "lever", "ashby", "workable"} else None,
            "careers_url": enrich_leads._careers_url_for(l.source, l.company_slug, l),
        }

    return final, list(stub_dict.values()), industry_drops


# ---------- CLI ----------

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_discover(args) -> int:
    workdir = Path(args.workdir)
    routed, unknown_slugs = discover(
        stream_a_hits_path=Path(args.stream_a_hits) if args.stream_a_hits else workdir / "stream-a-hits.json",
        companies_dir=args.companies_dir,
        companies_root=args.companies_root,
        dedup_paths=args.dedup_from or [],
        freshness_days=args.freshness_days,
        yc_max_candidates=args.yc_max_candidates,
    )
    _write_json(workdir / "routed.json", [l.to_dict() for l in routed])
    _write_json(workdir / "unknown-slugs.json", unknown_slugs)

    by_priority: dict[str, int] = {}
    by_stream: dict[str, int] = {}
    for l in routed:
        by_priority[l.priority] = by_priority.get(l.priority, 0) + 1
        by_stream[l.stream or "?"] = by_stream.get(l.stream or "?", 0) + 1

    print(json.dumps({
        "phase": "discover",
        "routed_total": len(routed),
        "by_priority": by_priority,
        "by_stream": by_stream,
        "unknown_slugs_count": len(unknown_slugs),
        "workdir": str(workdir),
        "routed_path": str(workdir / "routed.json"),
        "unknown_slugs_path": str(workdir / "unknown-slugs.json"),
    }, indent=2))
    return 0


def cmd_finalize(args) -> int:
    workdir = Path(args.workdir)
    routed_path = workdir / "routed.json"
    if not routed_path.exists():
        print(f"ERROR: {routed_path} not found. Run `pipeline.py discover` first.", file=sys.stderr)
        return 1
    routed = [LeadRecord.from_dict(d) for d in json.loads(routed_path.read_text())]

    industry: dict = {}
    if args.industry:
        ip = Path(args.industry)
        if ip.exists():
            industry = json.loads(ip.read_text()) or {}

    final, stubs, drops = finalize(
        routed=routed,
        industry=industry,
        max_total=args.max_total,
        known_good_cap=args.known_good_cap,
        in_review_cap=args.in_review_cap,
        new_discovery_cap=args.new_discovery_cap,
        companies_root=args.companies_root,
        preferences_path="context/preferences.md",
    )

    _write_json(workdir / "final.json", [l.to_dict() for l in final])
    _write_json(workdir / "stubs.json", stubs)

    # Optionally write the stubs to disk
    stub_results = None
    if args.write_stubs:
        stub_results = auto_stub.write_stubs(stubs, args.companies_root)

    # Summary
    by_priority: dict[str, int] = {}
    by_stream: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for l in final:
        by_priority[l.priority] = by_priority.get(l.priority, 0) + 1
        by_stream[l.stream or "?"] = by_stream.get(l.stream or "?", 0) + 1
        by_confidence[l.match_confidence] = by_confidence.get(l.match_confidence, 0) + 1
        by_source[l.source] = by_source.get(l.source, 0) + 1

    summary = {
        "phase": "finalize",
        "final_total": len(final),
        "industry_drops": len(drops),
        "industry_drop_details": drops,
        "by_priority": by_priority,
        "by_confidence": by_confidence,
        "by_source": by_source,
        "by_stream": by_stream,
        "stubs_to_create": len(stubs),
        "final_path": str(workdir / "final.json"),
        "stubs_path": str(workdir / "stubs.json"),
    }
    if stub_results is not None:
        summary["stubs_written"] = stub_results["summary"]
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    # discover
    d = sub.add_parser("discover", help="Run streams A/B/C, merge/dedup/route")
    d.add_argument("--workdir", default=".cache/find-roles")
    d.add_argument("--stream-a-hits", help="Path to JSON file with Stream A URL hits (default: <workdir>/stream-a-hits.json)")
    d.add_argument("--companies-dir", default="companies/interested")
    d.add_argument("--companies-root", default="companies")
    d.add_argument("--dedup-from", action="append", default=[])
    d.add_argument("--freshness-days", type=int, default=90)
    d.add_argument("--yc-max-candidates", type=int, default=40)

    # finalize
    f = sub.add_parser("finalize", help="Apply industry verdicts, sort, cap, optionally write stubs")
    f.add_argument("--workdir", default=".cache/find-roles")
    f.add_argument("--industry", help="Path to JSON file with industry verdicts (default: <workdir>/industry.json)")
    f.add_argument("--companies-root", default="companies")
    f.add_argument("--max-total", type=int, default=80)
    f.add_argument("--known-good-cap", type=int, default=30)
    f.add_argument("--in-review-cap", type=int, default=10)
    f.add_argument("--new-discovery-cap", type=int, default=40)
    f.add_argument("--write-stubs", action="store_true")

    args = ap.parse_args()
    if args.cmd == "discover":
        return cmd_discover(args)
    return cmd_finalize(args)


if __name__ == "__main__":
    sys.exit(main())
