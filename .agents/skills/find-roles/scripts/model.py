"""LeadRecord: the shared shape every ATS adapter returns.

A LeadRecord is one open role surfaced by the discovery phase. It carries enough
information to dedupe against existing applications and decide whether to draft,
but does NOT carry the verbatim JD or form-question schema. Those are fetched in
the drafting phase, only for leads the user greenlights.

Frozen for safety (no accidental in-place mutation between pipeline stages) and
hashability (set-based dedup in enrich_leads). All "mutations" are explicit
``dataclasses.replace`` calls.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class LeadRecord:
    # Identity
    company_slug: str
    ats_id: str
    title: str
    posting_url: str

    # Source
    source: str  # 'greenhouse' | 'lever' | 'ashby' | 'workday' | 'smartrecruiters' | 'workable' | 'custom'

    # Filtering signal
    location: str = ""
    department: str = ""
    posted_at: Optional[str] = None  # ISO date YYYY-MM-DD; None if unknown
    comp_min: Optional[int] = None
    comp_max: Optional[int] = None

    # Content
    content_excerpt: str = ""  # first ~500 chars of JD, optional

    # Match scoring (set by orchestrator, not adapter)
    match_confidence: str = ""  # 'high' | 'medium' | 'low'; empty if not yet scored
    match_reasons: tuple[str, ...] = ()  # tuple (not list) because frozen dataclass must be hashable

    # v2 additions (set by streams + enrich_leads.py)
    stream: str = ""              # 'A' (title-wide) | 'B' (sweep) | 'C' (YC) | ''
    priority: str = ""            # 'known-good' | 'in-review' | 'new-discovery' | ''
    company_name: str = ""        # extracted from posting page; fallback to Title-cased slug
    industry_check: str = ""      # 'clean' | 'blocked' | 'skipped' | 'n/a' | ''
    industry_check_reason: str = ""

    # Soft scoring (set by pipeline.finalize). NOT a filter — used as secondary
    # sort key so leads at companies matching preferences.md.company.industries_want
    # float higher within their priority bucket.
    industry_match: int = 0       # 0 = no overlap; 1 = at least one wanted-industry tag matches

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # match_reasons may be a tuple — JSON-serialize as a list
        if isinstance(d.get("match_reasons"), tuple):
            d["match_reasons"] = list(d["match_reasons"])
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "LeadRecord":
        keep = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        # match_reasons may arrive as list (from JSON); convert to tuple
        if "match_reasons" in keep and isinstance(keep["match_reasons"], list):
            keep["match_reasons"] = tuple(keep["match_reasons"])
        return cls(**keep)


def dump_leads(leads: list[LeadRecord]) -> str:
    """Serialize a list of LeadRecord to a single JSON array string."""
    return json.dumps([lead.to_dict() for lead in leads], ensure_ascii=False, indent=2)
