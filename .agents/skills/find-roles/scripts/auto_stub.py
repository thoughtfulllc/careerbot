"""Auto-stub creation for new-discovery companies surfaced by find-roles.

Reads the stubs-to-create list emitted by enrich_leads.py phase=finalize and
writes minimal company markdown files to companies/in-review/<slug>.md.

Each stub has frontmatter only (no body). Skipped if file already exists or if
the slug already lives in companies/{interested,in-review,not-interested}/.

Usage:
    python3 lib/auto_stub.py < /tmp/find-roles/stubs.json
    python3 lib/auto_stub.py --input /tmp/find-roles/stubs.json --companies-root companies

See SPEC.md §14.6.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def quote_value(val) -> str:
    if val is None or val == "":
        return "null"
    s = str(val)
    risky = (
        any(c in s for c in [":", "#", "'", '"'])
        or s.startswith(("-", "*", "&", "!", "?", "|", ">", "%", "@", "`"))
        or " " in s
    )
    if risky:
        # Escape any inner double quotes
        return f'"{s.replace(chr(34), chr(92) + chr(34))}"'
    return s


def stub_body(stub: dict, today: str) -> str:
    """Generate the YAML frontmatter for one stub. Body is empty by spec."""
    # Filename + canonical slug are lowercase per repo convention; ats_slug
    # preserves source case (Ashby/Workday URLs can be case-sensitive).
    canonical_slug = stub["slug"].lower()
    fields = [
        ("name", stub.get("name") or canonical_slug),
        ("slug", canonical_slug),
        ("industry", "[]"),  # literal empty list
        ("match_score", "null"),
        ("headcount", "null"),
        ("stage", "null"),
        ("valuation", "null"),
        ("hq", "null"),
        ("offices", "[]"),
        ("remote_policy", "null"),
        ("careers_url", stub.get("careers_url")),
        ("ats", stub.get("ats")),
        ("ats_slug", stub.get("ats_slug")),
        ("discovered_via", "find-roles"),
        ("researched_on", today),
        ("not_interested_reason", "null"),
    ]
    lines = ["---"]
    for k, v in fields:
        # For pre-formatted YAML literals (null, []), pass through
        if v in ("null", "[]"):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {quote_value(v)}")
    lines.append("---")
    lines.append("")  # trailing newline before empty body
    return "\n".join(lines) + "\n"


def slug_exists_anywhere(companies_root: Path, slug: str) -> Path | None:
    """Check for the slug in any case (filesystem may or may not be case-sensitive)."""
    needle = slug.lower()
    for status in ["interested", "in-review", "not-interested"]:
        d = companies_root / status
        if not d.exists():
            continue
        for p in d.glob("*.md"):
            if p.stem.lower() == needle:
                return p
    return None


def write_stubs(stubs: list[dict], companies_root: str, dry_run: bool = False) -> dict:
    """Write minimal stubs to companies/in-review/. Importable + idempotent.

    Returns the summary dict (matches the CLI output shape).
    """
    today = dt.date.today().isoformat()
    root = Path(companies_root)
    in_review = root / "in-review"
    if not dry_run:
        in_review.mkdir(parents=True, exist_ok=True)

    results = {"created": [], "skipped_exists": [], "errors": []}
    for stub in stubs:
        slug = stub.get("slug")
        if not slug:
            results["errors"].append({"stub": stub, "error": "missing slug"})
            continue
        existing = slug_exists_anywhere(root, slug)
        if existing:
            results["skipped_exists"].append({"slug": slug, "path": str(existing)})
            continue
        path = in_review / f"{slug.lower()}.md"
        content = stub_body(stub, today)
        if dry_run:
            results["created"].append({"slug": slug, "path": str(path), "dry_run": True})
        else:
            try:
                path.write_text(content)
                results["created"].append({"slug": slug, "path": str(path)})
            except Exception as e:
                results["errors"].append({"slug": slug, "error": str(e)})
    return {
        "summary": {
            "created": len(results["created"]),
            "skipped_exists": len(results["skipped_exists"]),
            "errors": len(results["errors"]),
        },
        "details": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="JSON file with stubs list. Default: stdin.")
    ap.add_argument("--companies-root", default="companies")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.input:
        stubs = json.loads(Path(args.input).read_text())
    else:
        stubs = json.loads(sys.stdin.read())

    report = write_stubs(stubs, args.companies_root, dry_run=args.dry_run)
    print(json.dumps(report, indent=2))
    return 0 if not report["details"]["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
