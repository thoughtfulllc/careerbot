"""Industry hard-filter check for unknown companies.

Pure-Python analyzer. The actual WebSearch + WebFetch calls happen at the
skill-prompt level (Claude tools); this script consumes the gathered text and
emits a verdict per company-slug.

Protocol:
- stdin: JSON object mapping `slug -> {company_name, search_hits, homepage_text}`
  where search_hits is a list of {title, url, description} from WebSearch.
- stdout: JSON object mapping `slug -> {status, reason, matched_keywords, sources}`
  where status is one of "clean" | "blocked" | "skipped".

Decision rule:
- 2+ keyword matches across different sources (search hit, homepage)  → blocked
- exactly 1 match                                                       → skipped
- 0 matches                                                             → clean

See SPEC.md §14.3.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


DEFAULT_BLOCKERS = [
    # Defense / weapons
    r"\bdefense\s+(contract|customer|client|department)",
    r"\bdepartment\s+of\s+defense\b",
    r"\bDoD\b",
    r"\bmilitary\s+(contract|customer|application|deployment)",
    r"\b(weapons|weaponry|weapon\s+systems?)\b",
    r"\blethal\s+autonomous",
    r"\bautonomous\s+weapons?\b",
    r"\bdrone\s+(strike|warfare|targeting)",
    r"\bsurveillance\s+(contract|customer|state)",
    r"\bintelligence\s+(community|agency|contract)",
    r"\bspy\s+(satellite|agency)",
    r"\bnational\s+security\s+customers?\b",
    r"\b(NGA|CIA|NSA|FBI|ICE)\s+(contract|customer|client)",
    # Gambling
    r"\bgambling\b",
    r"\bcasino\b",
    r"\bsportsbook\b",
    r"\bbetting\s+(platform|app|operator)",
    r"\bigaming\b",
]


def load_blockers(preferences_path: Optional[str]) -> list[re.Pattern]:
    """Load blocker keyword regexes. Tries preferences.md first; falls back to defaults."""
    patterns = []
    if preferences_path:
        try:
            text = Path(preferences_path).read_text()
            # Look for find_roles.industry_check_blockers in frontmatter
            in_blockers = False
            for line in text.splitlines():
                stripped = line.strip()
                if "industry_check_blockers:" in stripped:
                    in_blockers = True
                    continue
                if in_blockers:
                    if stripped.startswith("- "):
                        kw = stripped[2:].strip().strip('"').strip("'")
                        # Escape user-provided keywords; wrap in word boundaries
                        patterns.append(re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
                    elif stripped and not stripped.startswith("#"):
                        in_blockers = False
        except Exception:
            pass

    if not patterns:
        patterns = [re.compile(p, re.IGNORECASE) for p in DEFAULT_BLOCKERS]
    return patterns


def analyze_one(
    company_name: str,
    search_hits: list[dict],
    homepage_text: str,
    blockers: list[re.Pattern],
) -> dict:
    """Run the analyzer for one slug. Returns verdict dict."""
    # Build (source_label, text) pairs to scan
    sources: list[tuple[str, str]] = []
    for i, hit in enumerate(search_hits or []):
        blob = " ".join(filter(None, [hit.get("title", ""), hit.get("description", "")]))
        if blob:
            sources.append((f"search_hit_{i}:{hit.get('url', '')[:80]}", blob))
    if homepage_text:
        sources.append(("homepage", homepage_text[:20_000]))

    # Count matches per source
    matches_per_source: list[tuple[str, list[str]]] = []
    all_kws: set[str] = set()
    for label, text in sources:
        hits_here: list[str] = []
        for pat in blockers:
            if pat.search(text):
                hits_here.append(pat.pattern)
                all_kws.add(pat.pattern)
        if hits_here:
            matches_per_source.append((label, hits_here))

    n_sources_with_match = len(matches_per_source)

    if n_sources_with_match >= 2:
        status = "blocked"
        reason = f"{n_sources_with_match} sources matched blocker keywords"
    elif n_sources_with_match == 1:
        status = "skipped"
        reason = "1 source matched; surface with flag for user triage"
    else:
        status = "clean"
        reason = "no blocker keywords matched"

    return {
        "status": status,
        "reason": reason,
        "matched_keywords": sorted(all_kws),
        "sources": [{"label": label, "matches": hits} for label, hits in matches_per_source],
        "company_name": company_name,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preferences", default="context/preferences.md", help="Path to preferences.md (for blocker list)")
    ap.add_argument("--input", help="Read input JSON from this file instead of stdin")
    args = ap.parse_args()

    if args.input:
        data = json.loads(Path(args.input).read_text())
    else:
        data = json.loads(sys.stdin.read())

    blockers = load_blockers(args.preferences)
    out = {}
    for slug, info in (data or {}).items():
        out[slug] = analyze_one(
            company_name=info.get("company_name", slug),
            search_hits=info.get("search_hits") or [],
            homepage_text=info.get("homepage_text") or "",
            blockers=blockers,
        )

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
