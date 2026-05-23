"""Preflight: cheap pre-run sanity checks. Surfaces fill-state issues so the
user can fix them before drafting essays.

See SPEC.md §5.10.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


CANONICAL_IDENTITY_SLUGS = {
    "legal-name", "preferred-name", "pronouns", "email", "phone", "location",
    "linkedin", "github", "twitter", "portfolio", "work-authorization",
    "visa-sponsorship", "start-date", "relocation-openness",
    "hybrid-onsite-availability", "referral-source", "prior-employer-history",
}


def fill_count(theme_dir: Path) -> tuple[int, int]:
    """Returns (filled, stubs) — files with non-empty body vs frontmatter-only."""
    if not theme_dir.exists():
        return (0, 0)
    filled = stubs = 0
    for md in theme_dir.glob("*.md"):
        text = md.read_text()
        body = _extract_body(text).strip()
        if body:
            filled += 1
        else:
            stubs += 1
    return (filled, stubs)


def _extract_body(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2]


def ats_coverage(dir_path: Path) -> dict:
    if not dir_path.exists():
        return {"total": 0, "resolved": 0, "unresolved": 0, "by_ats": {}}
    total = resolved = 0
    by_ats: dict[str, int] = {}
    unresolved: list[str] = []
    for md in sorted(dir_path.glob("*.md")):
        if md.name.startswith("."):
            continue
        total += 1
        text = md.read_text()
        ats = _grep_fm(text, "ats")
        if ats and ats != "custom":
            resolved += 1
            by_ats[ats] = by_ats.get(ats, 0) + 1
        else:
            unresolved.append(md.stem)
    return {"total": total, "resolved": resolved, "unresolved": len(unresolved), "by_ats": by_ats, "unresolved_slugs": unresolved}


def _grep_fm(text: str, key: str) -> str | None:
    import re
    m = re.search(rf"^{key}:\s*(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return None
    v = m.group(1).strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]
    if v.lower() == "null":
        return None
    return v


def identity_coverage(theme_dir: Path) -> dict:
    present = {p.stem for p in theme_dir.glob("*.md")} if theme_dir.exists() else set()
    missing = sorted(CANONICAL_IDENTITY_SLUGS - present)
    stubs = []
    for slug in present & CANONICAL_IDENTITY_SLUGS:
        text = (theme_dir / f"{slug}.md").read_text()
        if not _extract_body(text).strip():
            stubs.append(slug)
    return {"missing": missing, "stubs": sorted(stubs), "filled": sorted((present & CANONICAL_IDENTITY_SLUGS) - set(stubs))}


def main(repo_root: str = ".") -> int:
    root = Path(repo_root)
    ab = root / "answer-bank"
    co = root / "companies" / "interested"

    report = {
        "answer_bank": {
            theme: dict(zip(["filled", "stubs"], fill_count(ab / theme)))
            for theme in ["identity", "beliefs", "stories", "career", "skills", "voice"]
        },
        "ats_coverage": ats_coverage(co),
        "identity": identity_coverage(ab / "identity"),
        "warnings": [],
    }

    # Surface key warnings
    if report["answer_bank"]["voice"]["filled"] == 0:
        report["warnings"].append(
            "answer-bank/voice/ has 0 entries — essay synthesis will be degraded. "
            "Add at least 1-2 voice samples via /seed-answer-bank."
        )
    ats = report["ats_coverage"]
    if ats["total"] and ats["resolved"] / ats["total"] < 0.5:
        report["warnings"].append(
            f"Only {ats['resolved']}/{ats['total']} companies have `ats:` resolved. "
            "Unresolved companies fall back to custom HTML adapter (slower, less reliable). "
            "Run `python3 .agents/skills/find-roles/lib/backfill_ats_metadata.py --dir companies/interested`."
        )
    if report["identity"]["missing"] or report["identity"]["stubs"]:
        report["warnings"].append(
            f"Identity bank gaps: missing={report['identity']['missing']}, "
            f"stubs={report['identity']['stubs']}. Every drafted application will have TODO holes."
        )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
