"""Routing + scoring primitives shared by ``pipeline.py``.

This module is library-only — no CLI. It provides the pure-data helpers the
unified discovery pipeline relies on: frontmatter parsing, ATS-slug-to-company
reverse mapping, company-status lookup, lead serialization, and the rank
constants used to sort leads at the end of the finalize phase.

The route/finalize flow itself lives in ``scripts/pipeline.py``; both
``discover`` (Phase 1) and ``finalize`` (Phase 2) call into the helpers here.

See SPEC.md §14 + §18.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Optional

from scripts.model import LeadRecord


# ---------- YAML frontmatter parsing ----------

_FM_LINE = re.compile(r"^([a-zA-Z_]+):\s*(.+?)\s*$")


def parse_fm(text: str) -> dict[str, str]:
    """Tiny YAML frontmatter parser — handles only flat ``key: value`` lines."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    out = {}
    for line in parts[1].strip().splitlines():
        m = _FM_LINE.match(line.rstrip())
        if m:
            v = m.group(2).strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            out[m.group(1)] = v
    return out


# ---------- Company-status lookups ----------

def build_ats_to_slug_map(companies_root: str) -> dict[tuple[str, str], str]:
    """Map ``(ats, ats_slug) → canonical company slug``. Used to fix Stream A leads
    whose ATS slug doesn't match the local company slug (e.g. anysphere → cursor)."""
    root = Path(companies_root)
    if not root.exists():
        return {}
    out = {}
    for status in ["interested", "in-review", "not-interested"]:
        d = root / status
        if not d.exists():
            continue
        for md in d.glob("*.md"):
            text = md.read_text()
            fm = parse_fm(text)
            ats = fm.get("ats")
            ats_slug = fm.get("ats_slug")
            slug = fm.get("slug") or md.stem
            if ats and ats_slug:
                out[(ats.lower(), ats_slug.lower())] = slug
    return out


def status_for_slug(slug: str, companies_root: str) -> str:
    """Returns one of ``known-good`` (interested) | ``in-review`` | ``not-interested`` | ``new-discovery``."""
    root = Path(companies_root)
    for status_folder, label in [
        ("interested", "known-good"),
        ("in-review", "in-review"),
        ("not-interested", "not-interested"),
    ]:
        if (root / status_folder / f"{slug}.md").exists():
            return label
    return "new-discovery"


# ---------- Lead JSON I/O ----------

def lead_from_dict(d: dict) -> LeadRecord:
    """Build a LeadRecord from a dict, ignoring extra fields gracefully."""
    fields = {f.name for f in dataclasses.fields(LeadRecord)}
    kept = {k: v for k, v in d.items() if k in fields}
    # Ensure required positional args are present
    kept.setdefault("company_slug", "")
    kept.setdefault("ats_id", "")
    kept.setdefault("title", "")
    kept.setdefault("posting_url", "")
    kept.setdefault("source", "")
    return LeadRecord(**kept)


def load_lead_list(path: str) -> list[LeadRecord]:
    """Read a JSON list of leads. Accepts either a bare list or ``{leads: [...]}``."""
    if not Path(path).exists():
        return []
    text = Path(path).read_text().strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("leads") or []
    return [lead_from_dict(d) for d in data]


def lead_to_dict(l: LeadRecord) -> dict:
    """Serialize one lead, dropping the optional ``raw`` debug payload."""
    d = dataclasses.asdict(l)
    d.pop("raw", None)
    return d


# ---------- Sort-key ranks (used by pipeline.finalize) ----------

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2, "": 3}
PRIORITY_RANK = {"known-good": 0, "in-review": 1, "new-discovery": 2, "": 3}


# ---------- Industry-want scoring (soft sort key, not a filter) ----------

def load_industries_want(path: str = "context/preferences.md") -> list[str]:
    """Parse ``company.industries_want`` from preferences.md frontmatter.

    Returns the human-readable strings (e.g. ``["Developer tools", "AI / ML
    products", "Health / biotech"]``). Tokenization happens inside
    ``score_industry_match`` so we keep this loader simple.
    """
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text()
    if not text.startswith("---"):
        return []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return []
    fm = parts[1]

    in_company = False
    in_industries_want = False
    out: list[str] = []
    for line in fm.splitlines():
        if line.rstrip() == "company:":
            in_company = True
            continue
        if in_company and line and not line.startswith(" "):
            # Out of company block
            break
        if not in_company:
            continue
        if line.startswith("  industries_want:"):
            in_industries_want = True
            continue
        if in_industries_want:
            if line.startswith("    - "):
                item = line[6:].strip().strip('"').strip("'")
                if item:
                    out.append(item)
            elif line.startswith("  ") and not line.startswith("    "):
                # Next field within company block — stop reading the list
                in_industries_want = False
    return out


def _tokenize(text: str) -> set[str]:
    """Lowercase + split on non-alphanumeric. ``"AI / ML products"`` → ``{"ai","ml","products"}``."""
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in {"and", "or", "the"}}


def score_industry_match(lead: LeadRecord, industries_want: list[str], companies_root: str) -> int:
    """Returns 1 if the lead's company has ``industry:`` tags that overlap with
    ``industries_want``, else 0.

    Soft signal — used by ``pipeline.finalize`` as a secondary sort key, NOT a
    filter. Leads at non-wanted-industry companies still surface; they just sort
    lower within their priority bucket.

    For new-discovery companies (whose stubs have ``industry: []``), this
    returns 0 since we don't yet know their industry. The user can promote them
    to ``interested/`` with proper tags later, after which subsequent runs will
    score them correctly.
    """
    if not industries_want:
        return 0
    slug = lead.company_slug
    if not slug:
        return 0

    # Find the company file; only look in interested/ + in-review/ (not
    # not-interested/, those leads are already dropped upstream)
    root = Path(companies_root)
    company_file = None
    for status in ["interested", "in-review"]:
        candidate = root / status / f"{slug}.md"
        if candidate.exists():
            company_file = candidate
            break
    if not company_file:
        return 0

    fm = parse_fm(company_file.read_text())
    industry_str = fm.get("industry", "")
    if not industry_str or industry_str in ("[]", ""):
        return 0

    # Parse YAML-list-as-inline-string: "[ai-ml, dev-tools, foundation-models]"
    cleaned = industry_str.strip("[]")
    tags = [t.strip().strip('"').strip("'").lower() for t in cleaned.split(",") if t.strip()]
    if not tags:
        return 0

    # Union all company-tag tokens
    company_tokens: set[str] = set()
    for tag in tags:
        company_tokens |= _tokenize(tag)
    if not company_tokens:
        return 0

    # Check overlap against each wanted industry
    for want in industries_want:
        want_tokens = _tokenize(want)
        if want_tokens & company_tokens:
            return 1
    return 0


# ---------- Stub-creation helpers ----------

def _title_case_slug(slug: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_]", slug))


def _careers_url_for(source: str, slug: str, lead: LeadRecord) -> Optional[str]:
    if source == "greenhouse":
        return f"https://job-boards.greenhouse.io/{slug}"
    if source == "lever":
        return f"https://jobs.lever.co/{slug}"
    if source == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    if source == "workable":
        return f"https://apply.workable.com/{slug}/"
    if lead.posting_url:
        from urllib.parse import urlparse
        p = urlparse(lead.posting_url)
        if p.netloc:
            return f"https://{p.netloc}/"
    return None
