"""Smoke tests for ATS adapters + filter primitives.

Run before relying on the pipeline in production. Catches ATS schema changes
(Workday especially) and regressions in title / location / freshness filtering.

    python3 scripts/test_adapters.py

Exits non-zero if any test fails. Network-required for adapter tests; if you're
offline, run with ``--filters-only`` to skip the live adapter calls.

Why not pytest: avoids the dependency. ~80 LOC of stdlib gets us per-component
smoke coverage that catches what matters (live API drift).
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

REPO_LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_LIB.parent))

from scripts.adapters import ashby, custom_html, greenhouse, lever, workable, workday
from scripts.adapters.base import AdapterError
from scripts.filters import classify_title, is_fresh, location_matches, parse_iso, parse_workday_relative
from scripts.model import LeadRecord
from scripts.role_config import RoleConfig


# Known-good company slugs per ATS — these should always have >0 active jobs.
# If any of these starts returning empty, either the company moved or the
# adapter is broken.
ADAPTER_FIXTURES = [
    ("greenhouse", "anthropic", lambda: greenhouse.fetch("anthropic", "anthropic")),
    ("lever",      "spotify",   lambda: lever.fetch("spotify", "spotify")),
    ("ashby",      "livekit",   lambda: ashby.fetch("livekit", "livekit")),
    ("workable",   "huggingface", lambda: workable.fetch("huggingface", "huggingface")),
    ("workday",    "adobe/wd5/external_experienced",
                                lambda: workday.fetch("adobe/wd5/external_experienced", "adobe")),
]


def test_adapters() -> list[tuple[str, bool, str]]:
    """Returns list of (test_name, passed, message)."""
    results = []
    for ats, slug, fn in ADAPTER_FIXTURES:
        name = f"adapter:{ats}({slug})"
        try:
            leads = fn()
        except AdapterError as e:
            results.append((name, False, f"AdapterError: {e}"))
            continue
        except Exception as e:
            results.append((name, False, f"unexpected: {e}\n{traceback.format_exc()}"))
            continue
        if not leads:
            results.append((name, False, "0 leads (board moved or API broken?)"))
            continue
        # Spot-check first lead shape
        first = leads[0]
        if not isinstance(first, LeadRecord):
            results.append((name, False, f"non-LeadRecord output: {type(first).__name__}"))
            continue
        if not first.ats_id or not first.title:
            results.append((name, False, f"missing ats_id/title in first lead: {first.to_dict()}"))
            continue
        results.append((name, True, f"{len(leads)} leads, sample: {first.title[:60]}"))
    return results


def test_filters() -> list[tuple[str, bool, str]]:
    """Title / location / freshness regression tests."""
    results = []

    title_cases = [
        ("Senior Product Designer", True, "high"),
        ("Sr. Product Designer", True, "high"),
        ("Staff Product Designer", True, "medium"),
        ("Design Engineer", True, "high"),
        ("Senior Design Engineer", True, "high"),
        ("UX Engineer", True, "high"),
        ("Design Technologist", True, "high"),
        ("Design Systems Engineer", True, "high"),
        ("Founding Designer", True, "low"),
        ("Product Design Lead", True, "low"),
        ("Brand Designer", True, "medium"),
        ("Senior Motion Designer", True, "medium"),
        ("Hardware Design Engineer", False, ""),
        ("Game Designer", False, ""),
        ("Design Manager", False, ""),
        ("Backend Engineer", False, ""),
        ("Systems Engineer", False, ""),  # excluded — non-design systems
    ]
    for title, want_match, want_conf in title_cases:
        matched, conf, _ = classify_title(title)
        ok = matched == want_match and conf == want_conf
        results.append((
            f"title:{title!r}",
            ok,
            f"got matched={matched} conf={conf!r} (want match={want_match} conf={want_conf!r})",
        ))

    location_cases = [
        ("San Francisco, CA", True),
        ("Remote (US)", True),
        ("Remote", True),
        ("New York, NY", True),
        ("Remote — Anywhere", True),
        ("London, UK", False),
        ("Remote (EMEA)", False),
        ("India only", False),
        ("Berlin, Germany", False),
    ]
    for loc, want in location_cases:
        matched, _ = location_matches(loc)
        ok = matched == want
        results.append((f"loc:{loc!r}", ok, f"got {matched}, want {want}"))

    # Freshness
    import datetime as dt
    today = dt.date(2026, 5, 22)
    fresh_cases = [
        ("2026-05-09", True),    # 13 days ago
        ("2025-12-01", False),   # 172 days ago
        (None, True),            # unknown → defaulted-fresh
    ]
    for posted, want in fresh_cases:
        fresh, _ = is_fresh(posted, cutoff_days=90, today=today)
        ok = fresh == want
        results.append((f"fresh:{posted!r}", ok, f"got {fresh}, want {want}"))

    # Date parsers
    iso_d = parse_iso("2026-05-09T14:32:00Z")
    results.append(("parse_iso", iso_d is not None and iso_d.isoformat() == "2026-05-09",
                    f"got {iso_d}"))
    wd_d = parse_workday_relative("Posted 3 Days Ago", today=today)
    results.append(("parse_workday_relative", wd_d is not None and (today - wd_d).days == 3,
                    f"got {wd_d}"))

    return results


def test_role_config() -> list[tuple[str, bool, str]]:
    """Verify RoleConfig produces expected patterns + queries for known preferences."""
    results = []

    # 1. Parse the user's actual preferences.md and check titles/specialties/track land correctly
    config = RoleConfig.from_preferences("context/preferences.md")
    results.append((
        "role_config:titles loaded",
        config.titles == ["Senior Product Designer", "Design Engineer"],
        f"got {config.titles}",
    ))
    results.append((
        "role_config:specialties loaded",
        config.specialties == ["Product/UX", "Visual/Brand", "Design systems", "Prototyping/motion"],
        f"got {config.specialties}",
    ))
    results.append((
        "role_config:track loaded",
        config.track == "IC",
        f"got {config.track!r}",
    ))
    results.append((
        "role_config:exclude_titles defaulted",
        config.exclude_titles == [],
        f"got {config.exclude_titles}",
    ))

    # 2. is_designer_family detection
    results.append((
        "role_config:is_designer_family detects design",
        config.is_designer_family(),
        f"got {config.is_designer_family()}",
    ))

    # 3. all_synonyms_for picks up the default registry
    syns = config.all_synonyms_for("Design Engineer")
    expected_subset = {"UX Engineer", "Design Technologist", "Design Systems Engineer"}
    missing = expected_subset - {s for s in syns}
    results.append((
        "role_config:synonyms-for-design-engineer",
        not missing,
        f"missing {missing} from {syns}",
    ))

    # 4. search_synonyms_for adds level-up variants
    search_syns = config.search_synonyms_for("Senior Product Designer")
    expected_search = {"Staff Product Designer", "Lead Product Designer", "Principal Product Designer"}
    missing_s = expected_search - {s for s in search_syns}
    results.append((
        "role_config:search-synonyms-include-staff+lead",
        not missing_s,
        f"missing {missing_s} from {search_syns[:8]}...",
    ))

    # 5. title_patterns generates non-empty compiled list
    patterns = config.title_patterns()
    results.append((
        "role_config:title_patterns non-empty",
        len(patterns) > 10,
        f"got {len(patterns)} patterns",
    ))

    # 6. exclude_patterns includes IC-track + designer-family + universal
    excludes = config.exclude_patterns()
    excl_text = " ".join(p.pattern for p in excludes)
    results.append((
        "role_config:excludes-include-manager",
        "manager" in excl_text,
        f"manager not found in excludes",
    ))
    results.append((
        "role_config:excludes-include-hardware",
        "hardware" in excl_text,
        f"hardware not found in excludes",
    ))
    results.append((
        "role_config:excludes-include-recruiter",
        "recruiter" in excl_text,
        f"recruiter not found in excludes",
    ))

    # 7. search_queries: 5 groups × 4 hosts = 20 (current preferences)
    queries = config.search_queries()
    results.append((
        "role_config:search_queries count",
        len(queries) == 20,
        f"got {len(queries)} queries (want 20)",
    ))

    # 8. classify_title via the default config matches expected verdicts
    title_cases = [
        ("Senior Product Designer", True, "high"),
        ("UX Engineer", True, "high"),                # via default registry synonym
        ("Brand Designer", True, "medium"),            # via specialty
        ("Design Systems Engineer", True, "high"),     # via specialty + default synonym
        ("Hardware Design Engineer", False, ""),       # designer-family exclude
        ("Engineering Manager", False, ""),            # IC-track exclude
        ("Recruiter, Design", False, ""),              # universal exclude
    ]
    for title, want_match, want_conf in title_cases:
        matched, conf, _ = classify_title(title, config=config)
        ok = matched == want_match and conf == want_conf
        results.append((
            f"role_config:classify({title!r})",
            ok,
            f"got matched={matched} conf={conf!r}",
        ))

    # 9. exclude_titles substring match — synthetic config with user-supplied excludes
    custom = RoleConfig(
        titles=["Senior Product Designer"],
        specialties=[],
        track="IC",
        exclude_titles=["Crypto Designer"],
        title_synonyms={},
    )
    matched, conf, _ = classify_title("Senior Crypto Designer at Web3 Co", config=custom)
    results.append((
        "role_config:user-exclude_titles-blocks",
        not matched,
        f"got matched={matched} conf={conf!r}",
    ))

    # 10. Different track changes excludes
    mgr_config = RoleConfig(
        titles=["Engineering Manager"],
        specialties=[],
        track="Management",
        exclude_titles=[],
        title_synonyms={},
    )
    matched, conf, _ = classify_title("Engineering Manager (IC)", config=mgr_config)
    results.append((
        "role_config:management-track-excludes-IC",
        not matched,
        f"got matched={matched} conf={conf!r}",
    ))

    return results


def test_industry_match() -> list[tuple[str, bool, str]]:
    """Industry-want scoring: soft signal, not a filter. See preferences.md.company.industries_want."""
    from scripts.enrich_leads import load_industries_want, score_industry_match
    results = []

    wants = load_industries_want("context/preferences.md")
    results.append((
        "industry_match:industries_want loaded",
        len(wants) >= 1,
        f"got {wants}",
    ))

    # 1. Known company with matching industry tags should score 1
    lead = LeadRecord(company_slug="anthropic", ats_id="x", title="x", posting_url="", source="greenhouse")
    score = score_industry_match(lead, wants, "companies")
    results.append((
        "industry_match:anthropic (ai-ml in wanted)",
        score == 1,
        f"got {score}",
    ))

    # 2. Linear (dev-tools) should score 1 — verifies the schema-drift fix
    lead = LeadRecord(company_slug="linear", ats_id="x", title="x", posting_url="", source="greenhouse")
    score = score_industry_match(lead, wants, "companies")
    results.append((
        "industry_match:linear (dev-tools in wanted)",
        score == 1,
        f"got {score}",
    ))

    # 3. Unknown / not-in-companies should score 0 (lead won't sort up via industry)
    lead = LeadRecord(company_slug="totally-made-up-no-file", ats_id="x", title="x", posting_url="", source="greenhouse")
    score = score_industry_match(lead, wants, "companies")
    results.append((
        "industry_match:unknown-slug scores 0",
        score == 0,
        f"got {score}",
    ))

    # 4. Empty industries_want returns 0 always (graceful no-op)
    lead = LeadRecord(company_slug="anthropic", ats_id="x", title="x", posting_url="", source="greenhouse")
    score = score_industry_match(lead, [], "companies")
    results.append((
        "industry_match:no-wanted-industries returns 0",
        score == 0,
        f"got {score}",
    ))

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--filters-only", action="store_true", help="Skip live adapter network tests")
    args = ap.parse_args()

    all_results: list[tuple[str, bool, str]] = []
    if not args.filters_only:
        all_results += test_adapters()
    all_results += test_filters()
    all_results += test_role_config()
    all_results += test_industry_match()

    fail_count = 0
    for name, passed, msg in all_results:
        mark = "PASS" if passed else "FAIL"
        if not passed:
            fail_count += 1
        print(f"  [{mark}] {name:55s} {msg}")
    print()
    print(f"{len(all_results)} tests, {fail_count} failures")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
