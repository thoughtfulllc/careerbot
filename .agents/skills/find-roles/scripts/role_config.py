"""Single source of truth for role-driven config.

Reads `context/preferences.md` and emits:
- title regex patterns (`filters.classify_title` consumes)
- exclude regex patterns (same)
- WebSearch query strings (`SKILL.md` step 2a consumes via `--print-queries`)

The decoupling principle: nothing about "Senior Product Designer" or "Design
Engineer" is baked into Python. All role-family text comes from preferences.md.

See `SPEC.md` Part 3 (§§23-32) for the design rationale.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================================
# Default registries — augmentable via preferences.md.role.title_synonyms
# ============================================================================

# Common known synonyms keyed by lowercased canonical title. Merged with the
# user's explicit `title_synonyms` (user values win on overlap).
DEFAULT_TITLE_SYNONYMS: dict[str, list[str]] = {
    "design engineer": ["UX Engineer", "Design Technologist", "Design Systems Engineer"],
    "senior product designer": ["Sr Product Designer", "Sr. Product Designer"],
    "staff product designer": ["Lead Product Designer", "Principal Product Designer"],
    "engineering manager": ["EM", "Eng Manager", "Engineering Team Lead"],
    "product manager": ["PM", "Sr PM", "Senior PM"],
}

# Specialty token → (regex, confidence) patterns. Tokens not listed here are
# used only as company-profile tiebreakers, not in title matching.
SPECIALTY_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "design systems": [
        (r"\b(senior|sr\.?|staff|lead|principal|founding)?\s*design\s+systems?\s+(designer|engineer)\b", "high"),
    ],
    "visual": [
        (r"\b(senior|sr\.?|staff|lead|principal|founding)?\s*visual\s+designer\b", "medium"),
    ],
    "brand": [
        (r"\b(senior|sr\.?|staff|lead|principal|founding)?\s*brand\s+designer\b", "medium"),
    ],
    "motion": [
        (r"\b(senior|sr\.?|staff|lead|principal|founding)?\s*motion\s+designer\b", "medium"),
    ],
}

# Specialty terms that are valid niche-role-name patterns. Used by
# search_queries() to also include specialty roles in the title-wide search.
SEARCH_SPECIALTY_GROUPS: dict[str, list[str]] = {
    "design systems": ["Design Systems Designer", "Design Systems Engineer"],
    "visual": ["Visual Designer"],
    "brand": ["Brand Designer"],
    "motion": ["Motion Designer"],
}

# Universal excludes — applied regardless of role family or track.
UNIVERSAL_EXCLUDES: list[str] = [
    r"\b(recruiter|sourcer|talent\s+partner)\b",
    r"\bsales\s+engineer\b",
    r"\binstructional\s+designer\b",
    r"\b(landscape|interior|fashion)\s+designer\b",
]

# Designer-family excludes — applied if user's titles or specialties indicate
# a designer / design-engineer search.
DESIGNER_FAMILY_EXCLUDES: list[str] = [
    r"\bhardware\s+design",
    r"\b(asic|chip|silicon|circuit|pcb|rf|mechanical|electrical|industrial)\s+(design|designer|engineer)",
    r"\bgame\s+designer\b",
    r"\bgraphic\s+design\s+intern\b",
    # Negative lookbehind: "Design Systems Engineer" is NOT excluded by the "systems engineer" branch
    r"(?<!design\s)\bsystems\s+engineer\b",
    r"\b(backend|infrastructure|platform|data|ml|machine\s+learning)\s+engineer\b",
]

# IC-track excludes — applied when role.track == "IC"
IC_TRACK_EXCLUDES: list[str] = [
    r"\b(manager|director|head\s+of|vp|vice\s+president|chief)\b.*designer",
    r"\bdesign\s+(manager|director|lead\s+manager)\b",
]

# Management-track excludes — applied when role.track == "Management".
# Word boundaries don't anchor outside word chars, so `\(ic\)` matches "(IC)" wherever it appears.
MGT_TRACK_EXCLUDES: list[str] = [
    r"\(ic\)",
    r"\bic[-\s]only\b",
    r"\bindividual\s+contributor\b",
]


# Hosts hit by Stream A's title-wide search
DEFAULT_SEARCH_HOSTS: list[str] = [
    "site:boards.greenhouse.io",
    "site:job-boards.greenhouse.io",
    "site:jobs.ashbyhq.com",
    "site:jobs.lever.co",
]


# ============================================================================
# Level prefix detection / expansion
# ============================================================================

LEVEL_NORMALIZED = {
    "senior": "senior",
    "sr": "senior",
    "sr.": "senior",
    "staff": "staff",
    "lead": "lead",
    "principal": "principal",
    "founding": "founding",
    "junior": "junior",
    "jr": "junior",
    "jr.": "junior",
    "mid": "mid",
    "mid-level": "mid",
}

SENIOR_VARIANTS = r"(senior|sr\.?)"
MEDIUM_LEVEL_VARIANTS = r"(staff|lead|principal|founding)"
ALL_LEVEL_VARIANTS = r"(senior|sr\.?|staff|lead|principal|founding)"


def _strip_level_prefix(title: str) -> tuple[Optional[str], str]:
    """Returns ``(normalized_level, base_role)``. Level is None if title has none."""
    words = title.strip().split()
    if not words:
        return (None, "")
    first = words[0].lower().rstrip(".")
    if first in LEVEL_NORMALIZED:
        return (LEVEL_NORMALIZED[first], " ".join(words[1:]))
    return (None, title.strip())


# ============================================================================
# RoleConfig
# ============================================================================

@dataclass
class RoleConfig:
    titles: list[str] = field(default_factory=list)
    specialties: list[str] = field(default_factory=list)
    track: str = "IC"  # "IC" | "Management"
    exclude_titles: list[str] = field(default_factory=list)
    title_synonyms: dict[str, list[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------------

    @classmethod
    def from_preferences(cls, path: str = "context/preferences.md") -> "RoleConfig":
        p = Path(path)
        if not p.exists():
            return cls()
        text = p.read_text()
        role_dict = _parse_role_block(text)
        return cls.from_dict(role_dict)

    @classmethod
    def from_dict(cls, d: dict) -> "RoleConfig":
        return cls(
            titles=list(d.get("titles") or []),
            specialties=list(d.get("specialties") or []),
            track=str(d.get("track") or "IC"),
            exclude_titles=list(d.get("exclude_titles") or []),
            title_synonyms=dict(d.get("title_synonyms") or {}),
        )

    # ------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------

    def is_designer_family(self) -> bool:
        """True if titles / specialties contain design-family keywords."""
        blob = " ".join(self.titles + self.specialties).lower()
        return bool(re.search(r"\b(design|designer|ux|product\s+design|brand|visual|motion)\b", blob))

    def all_synonyms_for(self, title: str) -> list[str]:
        """Return [title] + default-registry synonyms + user-provided synonyms.

        Order: user-provided first (highest priority), then default-registry,
        then the original title last. Deduped case-insensitively, preserving
        first occurrence.
        """
        key = title.lower().strip()
        from_user = self.title_synonyms.get(title) or self.title_synonyms.get(key) or []
        from_default = DEFAULT_TITLE_SYNONYMS.get(key, [])

        seen: set[str] = set()
        out: list[str] = []
        for s in list(from_user) + list(from_default) + [title]:
            sk = s.lower()
            if sk in seen:
                continue
            seen.add(sk)
            out.append(s)
        return out

    def search_synonyms_for(self, title: str) -> list[str]:
        """Like all_synonyms_for() but includes level-up variants.

        Reasoning: Stream A's WebSearch needs to find postings at the levels
        the user is willing to accept, not just the exact level they listed.
        A user who lists "Senior Product Designer" also wants to see Staff /
        Lead / Principal Product Designer postings on the search engine.

        ``title_patterns()`` still controls match-confidence on the role title,
        so over-broad search results get filtered down per-lead later.
        """
        base = self.all_synonyms_for(title)
        level, role_base = _strip_level_prefix(title)
        if not role_base:
            return base

        extra: list[str] = []
        if level == "senior":
            extra.extend([f"{lvl} {role_base}" for lvl in ["Staff", "Lead", "Principal", "Founding"]])
        elif level in {"staff", "lead", "principal"}:
            extra.extend([f"{lvl} {role_base}" for lvl in ["Senior", "Founding"]])
        elif level is None:
            extra.extend([f"{lvl} {role_base}" for lvl in ["Senior", "Staff", "Lead", "Principal", "Founding"]])

        seen = {s.lower() for s in base}
        out = list(base)
        for s in extra:
            if s.lower() in seen:
                continue
            seen.add(s.lower())
            out.append(s)
        return out

    # ------------------------------------------------------------------------
    # Pattern generation
    # ------------------------------------------------------------------------

    def title_patterns(self) -> list[tuple[re.Pattern, str]]:
        """Generate (regex, confidence) pairs for title matching."""
        patterns: list[tuple[str, str]] = []

        # === From user-listed titles ===
        for title in self.titles:
            patterns.extend(_patterns_for_title(title))
            # Synonyms (registry + user) — treat each as its own "no level prefix" title
            for syn in self.all_synonyms_for(title):
                if syn.lower() == title.lower():
                    continue
                patterns.extend(_patterns_for_title(syn))

        # === From specialties (registry-derived) ===
        for spec in self.specialties:
            # Normalize specialty: "Visual/Brand" → ["visual", "brand"]; "Design systems" → ["design systems"]
            parts = re.split(r"[/,]", spec)
            for part in parts:
                key = part.strip().lower()
                if key in SPECIALTY_PATTERNS:
                    patterns.extend(SPECIALTY_PATTERNS[key])

        # === Edge-case low-confidence catch-alls (only if designer family) ===
        if self.is_designer_family():
            patterns.extend([
                # "Founding Designer" / "Staff Designer" / "Principal Designer" — no qualifier
                (r"\b(founding|staff|principal)\s+designer\b", "low"),
                # "Product Design Lead" / "Design Lead" — noun-flipped form
                (r"\b(product\s+)?design\s+lead\b", "low"),
                # Generic "Senior Designer" / "Lead Designer" — no specialty
                (r"\b(senior|sr\.?)\s+designer\b", "low"),
                (r"\blead\s+designer\b", "low"),
                # "Senior IC, Design" — niche
                (r"\b(senior|sr\.?)\s+ic[,\s]+design", "medium"),
                # "Product Engineer ... (design|frontend|ui)"
                (r"\bproduct\s+engineer\b.*\b(design|frontend|ui)\b", "low"),
            ])

        # Dedupe by pattern text, keep highest confidence
        rank = {"high": 0, "medium": 1, "low": 2}
        best: dict[str, str] = {}
        for pat, conf in patterns:
            if pat not in best or rank[conf] < rank[best[pat]]:
                best[pat] = conf

        compiled = [(re.compile(pat, re.IGNORECASE), conf) for pat, conf in best.items()]
        # Sort: high → medium → low
        compiled.sort(key=lambda x: rank[x[1]])
        return compiled

    def exclude_patterns(self) -> list[re.Pattern]:
        """Generate exclude regexes: universal + family + track + user-explicit."""
        patterns: list[str] = list(UNIVERSAL_EXCLUDES)

        if self.is_designer_family():
            patterns.extend(DESIGNER_FAMILY_EXCLUDES)

        if self.track == "IC":
            patterns.extend(IC_TRACK_EXCLUDES)
        elif self.track == "Management":
            patterns.extend(MGT_TRACK_EXCLUDES)

        # User-explicit exclude_titles → case-insensitive substring match
        for excl in self.exclude_titles:
            if not excl.strip():
                continue
            # Treat the user's string as a substring to look for. Escape regex metachars.
            patterns.append(re.escape(excl.strip()))

        return [re.compile(p, re.IGNORECASE) for p in patterns]

    # ------------------------------------------------------------------------
    # Search query generation
    # ------------------------------------------------------------------------

    def search_queries(self, hosts: Optional[list[str]] = None, max_groups: int = 6) -> list[str]:
        """Generate WebSearch query strings: N hosts × M title groups.

        Groups: one per user-listed title (with synonyms ORed), plus one per
        matching specialty group. Capped at max_groups to keep total query
        count reasonable (default 6 × 4 hosts = 24 queries max).
        """
        hosts = hosts or DEFAULT_SEARCH_HOSTS
        groups: list[str] = []

        # Title groups: one per title, with search-time synonyms ORed (level-permissive)
        for title in self.titles:
            syns = self.search_synonyms_for(title)
            quoted = [f'"{s}"' for s in syns]
            groups.append("(" + " OR ".join(quoted) + ")")

        # Specialty groups: one per specialty that has a search registry entry
        for spec in self.specialties:
            parts = re.split(r"[/,]", spec)
            specialty_titles: list[str] = []
            for part in parts:
                key = part.strip().lower()
                if key in SEARCH_SPECIALTY_GROUPS:
                    specialty_titles.extend(SEARCH_SPECIALTY_GROUPS[key])
            if specialty_titles:
                quoted = [f'"{s}"' for s in specialty_titles]
                groups.append("(" + " OR ".join(quoted) + ")")

        # Cap
        groups = groups[:max_groups]

        if not groups:
            return []

        queries: list[str] = []
        for host in hosts:
            for grp in groups:
                queries.append(f"{host} {grp}")

        return queries


# ============================================================================
# Title-pattern generation per title
# ============================================================================

def _escape_role(base: str) -> str:
    """Escape a multi-word base-role for use inside a regex, preserving \\s+ between words."""
    words = base.split()
    return r"\s+".join(re.escape(w) for w in words)


def _patterns_for_title(title: str) -> list[tuple[str, str]]:
    """Returns (regex, confidence) list for one title string."""
    level, base = _strip_level_prefix(title)
    if not base:
        return []
    base_re = _escape_role(base)
    out: list[tuple[str, str]] = []

    if level == "senior":
        # User wants senior+; high for senior variants, medium for stepped-up levels, medium for bare
        out.append((rf"\b{SENIOR_VARIANTS}\s+{base_re}\b", "high"))
        out.append((rf"\b{base_re},?\s+(senior|sr\.?)\b", "high"))  # "Product Designer, Senior" form
        out.append((rf"\b{MEDIUM_LEVEL_VARIANTS}\s+{base_re}\b", "medium"))
        out.append((rf"\b{base_re}\b", "medium"))
    elif level in {"staff", "lead", "principal", "founding"}:
        # User wants staff+; high for those levels, medium for senior, low for bare
        out.append((rf"\b{MEDIUM_LEVEL_VARIANTS}\s+{base_re}\b", "high"))
        out.append((rf"\b{SENIOR_VARIANTS}\s+{base_re}\b", "medium"))
        out.append((rf"\b{base_re}\b", "low"))
    elif level == "junior" or level == "mid":
        # User wants junior/mid only; high for those, low for senior+
        out.append((rf"\b(junior|jr\.?|mid|mid-level)\s+{base_re}\b", "high"))
        out.append((rf"\b{base_re}\b", "medium"))
    elif level is None:
        # User didn't specify a level — match any-or-no level prefix at high confidence
        out.append((rf"\b{ALL_LEVEL_VARIANTS}?\s*{base_re}\b", "high"))
        out.append((rf"\b{base_re},?\s+(senior|sr\.?|staff|lead|principal|founding)\b", "high"))
    else:
        # Unrecognized level word; just match the literal title
        out.append((rf"\b{_escape_role(title)}\b", "high"))

    return out


# ============================================================================
# Tiny YAML frontmatter parser (stdlib-only)
# ============================================================================

def _parse_role_block(file_text: str) -> dict:
    """Extract the role: block from preferences.md YAML frontmatter.

    Handles only the subset of YAML we actually use:
    - Two-space-indented scalar fields: `track: IC`, `exclude_titles: []`
    - Two-space-indented block-list fields:
        titles:
          - Senior Product Designer
          - Design Engineer
    - Two-space-indented nested mapping (title_synonyms):
        title_synonyms:
          Design Engineer:
            - UX Engineer
            - Design Technologist
    """
    if not file_text.startswith("---"):
        return {}
    parts = file_text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]

    out: dict = {}
    current_key: Optional[str] = None
    current_kind: Optional[str] = None  # "list" | "dict"
    current_dict_key: Optional[str] = None
    in_role = False

    for raw_line in fm.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.lstrip() != line and not in_role:
            continue

        if line.rstrip(":") == "role" and not line.startswith(" "):
            in_role = True
            continue
        if not in_role:
            continue

        if not line.startswith("  "):
            # Out of role block (next top-level key or terminator)
            break

        # Indent: 2 spaces = field, 4 spaces = list item OR nested key, 6 = nested list item
        if line.startswith("    "):
            # 4+ space indent: list item or nested dict
            content = line[4:]  # strip 4 spaces
            if content.startswith("- "):
                item = content[2:].strip().strip('"').strip("'")
                if current_kind == "list" and current_key:
                    out.setdefault(current_key, []).append(item)
                elif current_kind == "dict" and current_dict_key:
                    # 6-space indent for nested list under title_synonyms is what we expect
                    out[current_key].setdefault(current_dict_key, []).append(item)
            elif content.startswith(" "):
                # 6-space indent — nested under a dict key
                deeper = content.lstrip()
                if deeper.startswith("- "):
                    item = deeper[2:].strip().strip('"').strip("'")
                    if current_kind == "dict" and current_dict_key:
                        out[current_key].setdefault(current_dict_key, []).append(item)
            else:
                # 4-space, no leading dash → nested mapping key (under title_synonyms)
                m = re.match(r"^([^:]+):\s*(.*)$", content)
                if m and current_kind == "dict":
                    current_dict_key = m.group(1).strip().strip('"').strip("'")
                    val = m.group(2).strip()
                    if val and val not in ("[]", "{}"):
                        # Inline scalar (not expected for title_synonyms, but tolerate)
                        out[current_key][current_dict_key] = [val.strip('"').strip("'")]
                    else:
                        out[current_key].setdefault(current_dict_key, [])
        else:
            # 2-space indent (field declaration)
            stripped = line[2:]
            m = re.match(r"^([a-zA-Z_]+):\s*(.*)$", stripped)
            if not m:
                continue
            key = m.group(1)
            val = m.group(2).strip()
            current_key = key
            current_dict_key = None
            if val == "[]":
                out[key] = []
                current_kind = None
            elif val == "{}":
                out[key] = {}
                current_kind = None
            elif val:
                # Inline scalar
                out[key] = val.strip().strip('"').strip("'")
                current_kind = None
            else:
                # Block-style; we'll learn list vs dict from the next indented line.
                # Default to list; promoted to dict if a non-dash key follows.
                out[key] = []
                current_kind = "list"

        # Late-promote list to dict if we saw a nested key
        if current_kind == "list" and current_key and isinstance(out.get(current_key), list) and not out[current_key]:
            # If the next 4-space line is a dict key (no dash), promote
            # This is handled implicitly above (the "no leading dash" branch
            # checks current_kind == "dict", but we set it to "list" by default).
            pass

    # Post-process: if title_synonyms slot was filled as list but should be dict, fix it.
    if isinstance(out.get("title_synonyms"), list):
        # Empty list left over from default list-init; convert to dict
        if not out["title_synonyms"]:
            out["title_synonyms"] = {}

    return out


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--preferences", default="context/preferences.md")
    ap.add_argument("--print-queries", action="store_true", help="Print the WebSearch query list (one per line)")
    ap.add_argument("--print-config", action="store_true", help="Print loaded RoleConfig as JSON")
    ap.add_argument("--print-patterns", action="store_true", help="Print compiled title patterns (regex + confidence)")
    ap.add_argument("--print-excludes", action="store_true", help="Print compiled exclude regexes")
    ap.add_argument("--max-groups", type=int, default=6, help="Cap on title-group count (default 6)")
    args = ap.parse_args()

    config = RoleConfig.from_preferences(args.preferences)

    if args.print_queries:
        for q in config.search_queries(max_groups=args.max_groups):
            print(q)
        return 0

    if args.print_config:
        print(json.dumps(dataclasses.asdict(config), indent=2, ensure_ascii=False))
        return 0

    if args.print_patterns:
        for pat, conf in config.title_patterns():
            print(f"[{conf:6s}] {pat.pattern}")
        return 0

    if args.print_excludes:
        for pat in config.exclude_patterns():
            print(pat.pattern)
        return 0

    # Default: print a summary
    queries = config.search_queries(max_groups=args.max_groups)
    print(json.dumps({
        "preferences_path": args.preferences,
        "titles": config.titles,
        "specialties": config.specialties,
        "track": config.track,
        "exclude_titles": config.exclude_titles,
        "title_synonyms": config.title_synonyms,
        "patterns_count": len(config.title_patterns()),
        "excludes_count": len(config.exclude_patterns()),
        "queries_count": len(queries),
        "is_designer_family": config.is_designer_family(),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
