"""Filter primitives: title matching, location matching, freshness gating.

- ``classify_title(title, config=None) -> (matched, confidence, reason)`` — uses
  the default RoleConfig loaded from `context/preferences.md` if none passed.
- ``location_matches(posting_location) -> (matched, reason)``
- ``is_fresh(posted_at_iso, cutoff_days) -> (fresh, reason)``
- Per-ATS date parsing helpers for adapters: ``parse_iso``, ``parse_epoch_ms``,
  ``parse_workday_relative``.

Title patterns + excludes are no longer hardcoded constants. They come from
``scripts.role_config.RoleConfig``, which reads ``preferences.md``. See SPEC §§23-32.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from scripts.role_config import RoleConfig

# ============================================================================
# Title matching
# ============================================================================

# Per-config compiled-pattern cache. Pipeline runs create one RoleConfig and reuse
# it; this cache keys by id(config) so the same RoleConfig doesn't re-compile.
_pattern_cache: dict[int, tuple[list[tuple[re.Pattern, str]], list[re.Pattern]]] = {}

# Lazy-loaded default config (used when caller doesn't pass one)
_default_config: "Optional[RoleConfig]" = None


def _get_default_config() -> "RoleConfig":
    global _default_config
    if _default_config is None:
        from scripts.role_config import RoleConfig
        _default_config = RoleConfig.from_preferences()
    return _default_config


def _get_compiled(config: "RoleConfig") -> tuple[list[tuple[re.Pattern, str]], list[re.Pattern]]:
    key = id(config)
    cached = _pattern_cache.get(key)
    if cached is not None:
        return cached
    compiled = (config.title_patterns(), config.exclude_patterns())
    _pattern_cache[key] = compiled
    return compiled


def classify_title(title: str, config: "Optional[RoleConfig]" = None) -> tuple[bool, str, str]:
    """Returns ``(matched, confidence, reason)``.

    Pulls patterns + excludes from the provided ``RoleConfig``. If none is
    passed, uses a process-wide singleton loaded from ``context/preferences.md``.
    """
    if not title:
        return (False, "", "empty title")
    if config is None:
        config = _get_default_config()
    patterns, excludes = _get_compiled(config)

    for ex in excludes:
        if ex.search(title):
            return (False, "", f"excluded: {ex.pattern}")

    for pat, conf in patterns:
        if pat.search(title):
            return (True, conf, f"matched: {pat.pattern}")

    return (False, "", "no pattern match")


# ============================================================================
# Location matching
# ============================================================================

# Hard blockers — international-only roles. Trailing word-boundary dropped on
# parenthesized forms because ``\b`` doesn't match between ``)`` and end-of-string.
_HARD_BLOCK = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(india|germany|france|uk|united\s+kingdom|ireland|netherlands|spain|portugal|poland|romania|brazil|argentina|mexico|canada|australia|japan|singapore|korea)\s+only\b",
        r"\b(emea|apac|latam)\s+only\b",
        r"\b(europe|asia)\s+only\b",
        r"\bremote\s+\(india\)",
        r"\bremote\s+\(emea\)",
        r"\bremote\s+\(apac\)",
        r"\bremote\s+\(uk\)",
        r"\bremote\s+\(europe\)",
        r"\bremote\s+\(germany\)",
        r"\bremote\s+\(france\)",
        r"\bremote\s+\(canada\)",
    ]
]

# US-allowed signals
_US_ALLOW = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bremote\b.*\b(us|usa|united\s+states|north\s+america|americas)\b",
        r"\bremote\s+\(?(us|usa|united\s+states|north\s+america)\)?\b",
        r"\b(us|usa|united\s+states|north\s+america)\s+remote\b",
        r"\bremote[-\s]*friendly\b",
        r"\bremote\s+\(?anywhere\)?\b",
        # Preferred cities
        r"\bsan\s+francisco\b",
        r"\bbay\s+area\b",
        r"\bnew\s+york\b",
        r"\bnyc\b",
        r"\bbrooklyn\b",
        r"\bmanhattan\b",
        r"\blos\s+angeles\b",
        r"\bsanta\s+monica\b",
        r"\bseattle\b",
        # Other US locations (acceptable under relocation flag)
        r"\b(austin|chicago|boston|denver|portland|atlanta|miami|nashville|raleigh|durham|cambridge|sunnyvale|mountain\s+view|palo\s+alto|menlo\s+park|cupertino|redmond|bellevue|kirkland|san\s+jose|san\s+diego|oakland|berkeley)\b",
        # State signals
        r"\b(california|new\s+york\s+state|new\s+york,|washington\s+state|washington,|oregon|texas|colorado|illinois|massachusetts|florida|georgia)\b",
        # Just "United States" or "US" mentioned
        r"\bunited\s+states\b",
        r"\busa?\b(?!\s*only)",
    ]
]

# Generic "remote" with no country qualifier — assume US unless blocked above
_GENERIC_REMOTE = re.compile(r"\bremote\b", re.IGNORECASE)


def location_matches(posting_location: str, open_to_relocation: bool = True) -> tuple[bool, str]:
    """Returns ``(matched, reason)``.

    Accepts the location string as posted (free text, comma-separated, etc.) and
    returns whether it falls within the user's accepted set, plus a short reason.
    """
    if not posting_location:
        # Empty location — accept; many roles list location later in JD body
        return (True, "no-location-listed")

    text = posting_location.strip()

    for blk in _HARD_BLOCK:
        if blk.search(text):
            return (False, f"international-only: {blk.pattern}")

    for ok in _US_ALLOW:
        if ok.search(text):
            return (True, f"us-allow: {ok.pattern}")

    if _GENERIC_REMOTE.search(text):
        return (True, "generic-remote (assumed-US)")

    return (False, "no-match")


# ============================================================================
# Freshness
# ============================================================================

def parse_iso(value: Optional[str]) -> Optional[dt.date]:
    """Parse Greenhouse / Ashby ISO timestamps (e.g. ``2026-05-09T14:32:00Z``)."""
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(v).date()
    except (ValueError, TypeError):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(value))
        if m:
            try:
                return dt.date.fromisoformat(m.group(1))
            except ValueError:
                return None
    return None


def parse_epoch_ms(value) -> Optional[dt.date]:
    """Parse Lever epoch-ms timestamps."""
    if value is None:
        return None
    try:
        ms = int(value)
        return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).date()
    except (ValueError, TypeError):
        return None


_WORKDAY_RELATIVE = re.compile(
    r"posted\s+(?:(?P<n>\d+)\+?\s+)?(?P<unit>today|day|week|month|year)s?\s*(?:ago)?",
    re.IGNORECASE,
)


def parse_workday_relative(value: Optional[str], today: Optional[dt.date] = None) -> Optional[dt.date]:
    """Parse Workday's relative dates: 'Posted Today', 'Posted 3 Days Ago', etc."""
    if not value:
        return None
    today = today or dt.date.today()
    m = _WORKDAY_RELATIVE.search(value)
    if not m:
        return None
    n = int(m.group("n") or 0)
    unit = m.group("unit").lower()
    if unit == "today":
        return today
    if unit == "day":
        return today - dt.timedelta(days=n)
    if unit == "week":
        return today - dt.timedelta(weeks=n)
    if unit == "month":
        return today - dt.timedelta(days=n * 30)
    if unit == "year":
        return today - dt.timedelta(days=n * 365)
    return None


def is_fresh(posted_at: Optional[str], cutoff_days: int = 90, today: Optional[dt.date] = None) -> tuple[bool, str]:
    """Returns ``(fresh, reason)``. None / unknown ``posted_at`` defaults to fresh."""
    if not posted_at:
        return (True, "no-date (defaulted-fresh)")
    try:
        posted = dt.date.fromisoformat(posted_at)
    except (ValueError, TypeError):
        return (True, f"unparseable-date:{posted_at} (defaulted-fresh)")
    today = today or dt.date.today()
    age = (today - posted).days
    if age < 0:
        return (True, f"future-posted:{posted_at}")
    return (age <= cutoff_days, f"posted {age}d ago")
