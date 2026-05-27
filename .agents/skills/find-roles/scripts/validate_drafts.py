#!/usr/bin/env python3
"""
Validate that drafted application files in applications/in-review/ match the
canonical lead metadata in .cache/find-roles/final.json.

Run at the end of /find-roles step 9 (Report back). Detects orchestrator
hand-typing errors that put wrong posted_at, location, salary, source, or url
into application frontmatter.

Exits 0 on full match, 1 on any mismatch. Prints a human-readable diff.

Usage:
    python3 validate_drafts.py [--final .cache/find-roles/final.json] \\
        [--apps-dir applications/in-review] [--strict]

Fields checked per (company_slug, ats_id) match in final.json:
    title, url, source, posted_at, location, salary_min, salary_max

The `date_found` field is set at draft time, not from final.json. It is NOT
checked (it should always be today, ISO format).

The `notes` and `company` fields are owned by the drafter / orchestrator. They
are NOT checked.

By default, files in apps-dir whose (company_slug, ats_id) isn't in final.json
are skipped silently — they predate this run. Use --strict to fail on unmatched
files too.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
KV_RE = re.compile(r'^([A-Za-z_]+):\s*(.*?)\s*$')

# Fields validated against final.json. Each entry is (frontmatter_key, lead_key, normalize_fn).
CHECKED_FIELDS = [
    ("title", "title", lambda v: v),
    ("url", "posting_url", lambda v: v),
    ("source", "source", lambda v: v),
    ("posted_at", "posted_at", lambda v: v),
    ("location", "location", lambda v: v),
    ("salary_min", "comp_min", lambda v: int(v) if v not in (None, "", "null") else None),
    ("salary_max", "comp_max", lambda v: int(v) if v not in (None, "", "null") else None),
]


def parse_yaml_string(raw: str):
    """Strip surrounding double quotes from a YAML string value if present."""
    raw = raw.strip()
    if raw == "null" or raw == "" or raw == "~":
        return None
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    return raw


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        kv = KV_RE.match(line)
        if not kv:
            continue
        fm[kv.group(1)] = parse_yaml_string(kv.group(2))
    return fm


def normalize_for_compare(val):
    if val in ("", "null", None):
        return None
    return val


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--final", default=".cache/find-roles/final.json")
    p.add_argument("--apps-dir", default="applications/in-review")
    p.add_argument("--strict", action="store_true",
                   help="Fail if an apps-dir file has (company_slug, ats_id) not present in final.json")
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON instead of human prose")
    args = p.parse_args()

    final_path = Path(args.final)
    apps_dir = Path(args.apps_dir)

    if not final_path.exists():
        print(f"FAIL: final.json not found at {final_path}", file=sys.stderr)
        return 2
    if not apps_dir.exists():
        print(f"FAIL: apps-dir not found at {apps_dir}", file=sys.stderr)
        return 2

    leads = json.loads(final_path.read_text())
    # Index by (company_slug, ats_id). ats_id can come back as int or str; normalize to str.
    by_id = {}
    for lead in leads:
        key = (lead["company_slug"], str(lead["ats_id"]))
        by_id[key] = lead

    # Three buckets:
    #   - regressions: final.json had a value, frontmatter dropped or contradicts it. FAIL.
    #     This is the original bug class (e.g., posted_at: null when adapter captured a date).
    #   - enrichments: final.json was null, frontmatter has a value (subagent extracted from JD).
    #     INFO only, not a failure — the file is more accurate than final.json.
    #   - disagreements: both non-null, different values. FAIL — real conflict.
    regressions: list[dict[str, Any]] = []
    enrichments: list[dict[str, Any]] = []
    unmatched_files: list[str] = []
    files_checked = 0

    for md_path in sorted(apps_dir.rglob("*.md")):
        text = md_path.read_text()
        fm = parse_frontmatter(text)
        if not fm:
            continue
        company = fm.get("company")
        ats_id = fm.get("ats_id")
        if not company or not ats_id:
            continue
        key = (str(company), str(ats_id))
        lead = by_id.get(key)
        if not lead:
            unmatched_files.append(str(md_path))
            continue
        files_checked += 1
        for fm_key, lead_key, normalize in CHECKED_FIELDS:
            fm_val = normalize_for_compare(fm.get(fm_key))
            try:
                lead_val = normalize(lead.get(lead_key))
            except (TypeError, ValueError):
                lead_val = lead.get(lead_key)
            lead_val = normalize_for_compare(lead_val)
            if str(fm_val) == str(lead_val):
                continue
            entry = {
                "file": str(md_path),
                "field": fm_key,
                "frontmatter": fm_val,
                "final_json": lead_val,
            }
            if lead_val is None and fm_val is not None:
                enrichments.append(entry)
            elif fm_val is None and lead_val is not None:
                # Regression: lost data the pipeline had.
                regressions.append(entry)
            else:
                # Both non-null and disagree.
                regressions.append(entry)

    if args.json:
        print(json.dumps({
            "files_checked": files_checked,
            "regressions": regressions,
            "enrichments": enrichments,
            "unmatched_files": unmatched_files,
        }, indent=2, default=str))
    else:
        print(f"Validated {files_checked} application files against {final_path}")
        if regressions:
            print(f"\n{len(regressions)} REGRESSION(s) — frontmatter dropped or contradicts final.json:")
            for m in regressions:
                print(f"  {m['file']}")
                print(f"    {m['field']}: frontmatter={m['frontmatter']!r}  final.json={m['final_json']!r}")
        else:
            print("No regressions: every value present in final.json is preserved in frontmatter.")
        if enrichments:
            print(f"\n{len(enrichments)} enrichment(s) — frontmatter has data the pipeline didn't capture (informational):")
            for m in enrichments[:20]:
                print(f"  {m['file']}")
                print(f"    {m['field']}: frontmatter={m['frontmatter']!r}  (final.json was null)")
            if len(enrichments) > 20:
                print(f"  ... and {len(enrichments) - 20} more")
        if unmatched_files:
            print(f"\n{len(unmatched_files)} file(s) in apps-dir not present in final.json (predate this run):")
            for f in unmatched_files[:10]:
                print(f"  {f}")
            if len(unmatched_files) > 10:
                print(f"  ... and {len(unmatched_files) - 10} more")

    if regressions:
        return 1
    if args.strict and unmatched_files:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
