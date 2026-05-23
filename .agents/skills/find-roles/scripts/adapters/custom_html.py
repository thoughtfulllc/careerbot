"""Custom HTML adapter — fallback for companies not on a known ATS.

Fetches the careers page HTML and extracts likely job links via regex on
anchor tags whose href matches /jobs/, /careers/, or /openings/ patterns.
Confidence is capped at 'medium' since the structured data is approximate.

The Claude harness can supplement with WebFetch for JS-heavy pages where this
adapter returns nothing.

See SPEC.md §5.2.6.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.adapters.base import AdapterError, http_get_text
from scripts.model import LeadRecord, dump_leads


_JOB_PATH_HINT = re.compile(r"/(jobs?|careers?|openings?|positions?|roles?|opportunities)/", re.IGNORECASE)
# Anchor patterns that should NOT be treated as job links
_SKIP_PATH = re.compile(r"/(blog|press|news|about|contact|faq|categories|topics|teams?)/", re.IGNORECASE)


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors: list[tuple[str, str]] = []  # (href, text)
        self._href = None
        self._text_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_d = dict(attrs)
            self._href = attrs_d.get("href")
            self._text_buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._text_buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._text_buf).split())
            self.anchors.append((self._href, text))
            self._href = None
            self._text_buf = []


def fetch(careers_url: str, company_slug: str) -> list[LeadRecord]:
    """Best-effort HTML scrape of a careers page."""
    if not careers_url:
        raise AdapterError("custom adapter requires a careers_url")

    try:
        html = http_get_text(careers_url)
    except AdapterError:
        raise

    parser = _AnchorCollector()
    try:
        parser.feed(html)
    except Exception as e:
        raise AdapterError(f"failed to parse HTML from {careers_url}: {e}") from e

    base = careers_url
    seen: set[str] = set()
    leads: list[LeadRecord] = []
    for href, text in parser.anchors:
        if not href:
            continue
        # Skip mailtos, anchors, JS handlers
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        full_url = urljoin(base, href)
        if not _JOB_PATH_HINT.search(urlparse(full_url).path):
            continue
        if _SKIP_PATH.search(urlparse(full_url).path):
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        # ATS ID guess: last URL segment
        ats_id = urlparse(full_url).path.rstrip("/").split("/")[-1]
        # Sanity: ats_id should look ID-ish, not a word like "engineering"
        if not re.search(r"\d|-{2,}|[A-Z]{2,}", ats_id) and len(ats_id) < 6:
            # Probably not a job link
            continue
        title = text.strip() or "(unknown title)"
        leads.append(LeadRecord(
            company_slug=company_slug,
            ats_id=ats_id,
            title=title,
            posting_url=full_url,
            source="custom",
            location="",
            posted_at=None,
            content_excerpt="",
        ))

    return leads


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: custom_html.py <careers_url> <company_slug>", file=sys.stderr)
        sys.exit(2)
    try:
        leads = fetch(sys.argv[1], sys.argv[2])
        print(dump_leads(leads))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
