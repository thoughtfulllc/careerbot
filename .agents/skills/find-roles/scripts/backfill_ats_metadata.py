"""One-shot migration: detect each company's ATS + slug, write back to frontmatter.

Walks `companies/interested/*.md`, reads each file's careers_url (or pulls one
from the "Careers page: <url>" line in the body if frontmatter is missing it),
fetches the URL, detects the ATS host, and writes `ats:` / `ats_slug:` /
`careers_url:` back to the frontmatter.

Idempotent — safe to re-run. Companies already resolved are skipped.

See SPEC.md §7.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO_LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_LIB.parent))  # so `lib.x` imports work

from scripts.adapters.base import USER_AGENT


# ATS host detectors. Each returns (ats, ats_slug) or (None, None).
def detect_from_url(url: str) -> tuple[str | None, str | None]:
    """Detect ATS + slug from a URL string alone (no fetch)."""
    if not url:
        return (None, None)
    p = urlparse(url)
    host = p.netloc.lower()
    path_parts = [s for s in p.path.split("/") if s]

    # Greenhouse: boards.greenhouse.io/<slug> or job-boards.greenhouse.io/<slug>
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io") and path_parts:
        return ("greenhouse", path_parts[0])

    # Lever: jobs.lever.co/<slug>
    if host == "jobs.lever.co" and path_parts:
        return ("lever", path_parts[0])

    # Ashby: jobs.ashbyhq.com/<slug>
    if host == "jobs.ashbyhq.com" and path_parts:
        return ("ashby", path_parts[0])

    # Workday: <tenant>.wd<N>.myworkdayjobs.com/<site> (path may be /en-US/<site> or just /<site>)
    m = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host)
    if m:
        tenant = m.group(1)
        wd = m.group(2)
        # Path: skip locale (en-US) if present, take next segment as site
        site = None
        for p_ in path_parts:
            if re.match(r"^[a-z]{2}-[a-z]{2}$", p_.lower()):
                continue
            site = p_
            break
        if site:
            return ("workday", f"{tenant}/{wd}/{site}")

    # SmartRecruiters: careers.smartrecruiters.com/<slug>
    if host == "careers.smartrecruiters.com" and path_parts:
        return ("smartrecruiters", path_parts[0])

    # Workable: apply.workable.com/<slug>
    if host == "apply.workable.com" and path_parts:
        return ("workable", path_parts[0])

    return (None, None)


# Patterns to find embedded ATS boards inside a fetched HTML page.
_EMBED_PATTERNS = [
    # Greenhouse — embed iframe or boards-api script reference
    (re.compile(r"boards\.greenhouse\.io/(?:embed/job_board\?for=)?([a-zA-Z0-9_-]+)", re.IGNORECASE), "greenhouse"),
    (re.compile(r"job-boards\.greenhouse\.io/([a-zA-Z0-9_-]+)", re.IGNORECASE), "greenhouse"),
    (re.compile(r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)/", re.IGNORECASE), "greenhouse"),
    # Lever
    (re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.IGNORECASE), "lever"),
    # Ashby
    (re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE), "ashby"),
    (re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([a-zA-Z0-9_-]+)", re.IGNORECASE), "ashby"),
    # Workday — tricky; capture tenant + wdN
    (re.compile(r"https://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[a-z0-9-]+/)?(?:[a-z]{2}-[a-z]{2}/)?([a-zA-Z0-9_-]+)", re.IGNORECASE), "workday"),
    # SmartRecruiters
    (re.compile(r"careers\.smartrecruiters\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE), "smartrecruiters"),
    (re.compile(r"api\.smartrecruiters\.com/v1/companies/([a-zA-Z0-9_-]+)/", re.IGNORECASE), "smartrecruiters"),
    # Workable
    (re.compile(r"apply\.workable\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE), "workable"),
]


_PROBE_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def probe_by_slug(slug: str, timeout: int = 10) -> tuple[str | None, str | None, str | None]:
    """Try each ATS API with `slug` as the board slug. Return first that returns
    a non-empty job list. Also tries common slug variants."""
    candidates = [slug, slug.replace("-", ""), slug.replace("-", "_"), slug.split("-")[0]]
    seen = set()
    for variant in candidates:
        if not variant or variant in seen:
            continue
        seen.add(variant)
        for ats, template in _PROBE_URLS.items():
            url = template.format(slug=variant)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            # Quick "this slug exists" check. We accept "board exists, no current
            # jobs" as a positive — it means the slug is bound to a real board
            # and a future run will pick up postings when they appear.
            try:
                data = json.loads(body)
            except Exception:
                continue
            # Greenhouse: existing board returns {"jobs": [...]} even if empty.
            # 404'd slugs error out at the request level (handled above).
            if ats == "greenhouse" and isinstance(data, dict) and "jobs" in data:
                return (ats, variant, None)
            # Lever: existing board returns a list (possibly empty); missing slugs
            # return {"ok": false, "error": "Document not found"}.
            if ats == "lever" and isinstance(data, list):
                return (ats, variant, None)
            # Ashby: existing board returns {"jobs": [...]} (possibly empty).
            if ats == "ashby" and isinstance(data, dict) and "jobs" in data:
                return (ats, variant, None)
    return (None, None, "no probe match")


def detect_from_html(url: str, timeout: int = 15) -> tuple[str | None, str | None, str | None]:
    """Fetch the URL and look for embedded ATS hints in the HTML.

    Returns (ats, ats_slug, error). Error is None on success or a short reason string."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            html = resp.read(500_000).decode("utf-8", errors="replace")  # cap at 500KB
    except urllib.error.HTTPError as e:
        return (None, None, f"http {e.code}")
    except urllib.error.URLError as e:
        return (None, None, f"url-error: {e.reason}")
    except Exception as e:
        return (None, None, f"fetch-failed: {e}")

    # Check if the final URL itself is an ATS URL
    ats, slug = detect_from_url(final_url)
    if ats:
        return (ats, slug, None)

    # Special handling for Workday: needs all three parts
    for m in re.finditer(
        r"https://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[a-z0-9-]+/)?(?:[a-z]{2}-[a-z]{2}/)?([a-zA-Z0-9_-]+)",
        html,
        re.IGNORECASE,
    ):
        tenant, wd, site = m.group(1), m.group(2), m.group(3)
        if site.lower() not in {"job", "jobs"}:
            return ("workday", f"{tenant}/{wd}/{site}", None)

    for pat, ats in _EMBED_PATTERNS:
        m = pat.search(html)
        if m:
            slug = m.group(1)
            # Filter common false positives
            if slug.lower() in {"v1", "v2", "api", "board", "boards", "embed", "css", "js", "image", "static"}:
                continue
            return (ats, slug, None)

    return (None, None, "no ats found in html")


# Body-scanning: extract a careers URL from the dossier body if frontmatter careers_url is missing
_BODY_CAREERS_PATTERNS = [
    # Known-ATS hosts win first
    re.compile(r"(https?://(?:boards\.greenhouse\.io|job-boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com|careers\.smartrecruiters\.com|apply\.workable\.com|[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)/[^\s)\]]+)", re.IGNORECASE),
    # "Careers page: <url>" prose
    re.compile(r"Careers?\s+page:?\s*(https?://\S+)", re.IGNORECASE),
    # Frontmatter-style hint
    re.compile(r"`?careers_url`?[:=]\s*(https?://\S+)", re.IGNORECASE),
    # Markdown link with /careers in path
    re.compile(r"\[(?:careers?\s+page|careers?|jobs|open\s+roles)[^\]]*\]\((https?://[^\s)]+)\)", re.IGNORECASE),
    # Any URL containing /careers or /jobs or /join (in markdown link or bare)
    re.compile(r"(https?://[a-z0-9.-]+/(?:careers?|jobs?|join|work-with-us)\b[^\s)\]]*)", re.IGNORECASE),
]


def extract_careers_url_from_body(body: str) -> str | None:
    """Find the best careers URL. Prefer index URLs (no /jobs/<id>) over individual postings."""
    candidates: list[str] = []
    for pat in _BODY_CAREERS_PATTERNS:
        for m in pat.finditer(body):
            candidates.append(m.group(1).rstrip(".,)"))
    if not candidates:
        return None

    def score(url: str) -> int:
        u = url.lower()
        # Lower is better
        if re.search(r"/jobs?/[a-z0-9-]{6,}", u):
            return 10  # individual posting
        if "/careers" in u or "/jobs" in u or "/join" in u:
            return 0  # index page
        return 5

    candidates.sort(key=score)
    return candidates[0]


# Frontmatter line-level handling: preserve everything except the keys we touch.
_FM_KEY_LINE = re.compile(r"^(?P<key>[a-zA-Z_]+)\s*:\s*(?P<value>.*)$")


def split_file(text: str) -> tuple[list[str], list[str], str]:
    """Returns (frontmatter_lines, body_lines, raw_separator).

    Frontmatter is between the first '---' line and the next '---' line.
    """
    if not text.startswith("---"):
        return ([], text.splitlines(keepends=True), "")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return ([], lines, "")
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            end = i
            break
    if end is None:
        return ([], lines, "")
    return (lines[1:end], lines[end + 1:], "---\n")


def parse_fm_lines(lines: list[str]) -> dict[str, tuple[int, str]]:
    """Return mapping key -> (line_index, value_string)."""
    out: dict[str, tuple[int, str]] = {}
    for i, line in enumerate(lines):
        m = _FM_KEY_LINE.match(line.rstrip("\n"))
        if m:
            out[m.group("key")] = (i, m.group("value").strip())
    return out


def quote_value(val: str) -> str:
    """Return a YAML-safe scalar — quote if it contains risky chars."""
    if val is None or val == "":
        return "null"
    risky = any(c in val for c in [":", "#", "'", '"']) or val.startswith(("-", "*", "&", "!", "?", "|", ">", "%", "@", "`"))
    if risky or " " in val:
        return f'"{val}"'
    return val


def upsert_fm_lines(fm_lines: list[str], updates: dict[str, str]) -> list[str]:
    """Insert or update each key in `updates` in the frontmatter lines.

    Insertion strategy: if key exists, replace its line in place. If new,
    insert just before any blank-trailing lines at the end of frontmatter.
    """
    parsed = parse_fm_lines(fm_lines)
    out = list(fm_lines)

    for key, val in updates.items():
        line = f"{key}: {quote_value(val)}\n"
        if key in parsed:
            idx, _ = parsed[key]
            out[idx] = line
        else:
            # Insert at end, before trailing blank lines
            insert_at = len(out)
            while insert_at > 0 and out[insert_at - 1].strip() == "":
                insert_at -= 1
            out.insert(insert_at, line)
            # Refresh parsed indices to keep subsequent inserts coherent
            parsed = parse_fm_lines(out)
    return out


def process_file(path: Path, force: bool = False, dry_run: bool = False) -> dict:
    """Returns a status dict for the migration report."""
    text = path.read_text()
    fm_lines, body_lines, _ = split_file(text)
    fm = parse_fm_lines(fm_lines)

    def fm_val(k: str) -> str | None:
        if k not in fm:
            return None
        v = fm[k][1].strip()
        # Strip optional quotes
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        return v

    slug = fm_val("slug") or path.stem
    existing_ats = fm_val("ats")
    existing_ats_slug = fm_val("ats_slug")
    existing_careers_url = fm_val("careers_url")

    if existing_ats and existing_ats_slug and not force:
        return {"slug": slug, "status": "skip-already-resolved", "ats": existing_ats, "ats_slug": existing_ats_slug}

    # Find a careers URL to work with
    careers_url = existing_careers_url
    if not careers_url:
        body_text = "".join(body_lines)
        careers_url = extract_careers_url_from_body(body_text)

    ats = ats_slug = None
    detect_method = ""
    error = None

    if careers_url:
        # URL-based detection first
        ats, ats_slug = detect_from_url(careers_url)
        detect_method = "url"
        if not ats:
            # Fetch + scan HTML
            ats, ats_slug, error = detect_from_html(careers_url)
            detect_method = "html"

    if not ats:
        # Last resort: try the company slug directly against each ATS API
        ats, ats_slug, probe_err = probe_by_slug(slug)
        if ats:
            detect_method = "probe"
            error = None
        else:
            error = f"{error}; probe: {probe_err}" if error else probe_err

    if not ats and not careers_url:
        return {"slug": slug, "status": "no-careers-url", "ats": None, "ats_slug": None, "error": error}

    # Normalize ats_slug case. ATS APIs are case-insensitive but lowercase is
    # the canonical form. Exception: Workday paths can be case-sensitive in
    # practice (e.g. 'External' is a Workday site name), so we keep their case.
    if ats_slug and ats and ats != "workday":
        ats_slug = ats_slug.lower()

    updates: dict[str, str] = {}
    if careers_url and not existing_careers_url:
        updates["careers_url"] = careers_url
    if ats:
        updates["ats"] = ats
    if ats_slug:
        updates["ats_slug"] = ats_slug

    if updates and not dry_run:
        new_fm = upsert_fm_lines(fm_lines, updates)
        new_text = "---\n" + "".join(new_fm) + "---\n" + "".join(body_lines)
        path.write_text(new_text)

    return {
        "slug": slug,
        "status": "resolved" if ats else "unresolved",
        "ats": ats,
        "ats_slug": ats_slug,
        "careers_url": careers_url,
        "detect": detect_method,
        "error": error,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="companies/interested", help="Directory of company .md files to backfill.")
    ap.add_argument("--force", action="store_true", help="Re-resolve even if ats/ats_slug already set.")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change without writing.")
    ap.add_argument("--report", default=None, help="Write a migration report to this path.")
    args = ap.parse_args()

    d = Path(args.dir)
    if not d.exists():
        print(f"ERROR: {d} does not exist", file=sys.stderr)
        return 1

    results = []
    for md in sorted(d.glob("*.md")):
        if md.name.startswith("."):
            continue
        try:
            r = process_file(md, force=args.force, dry_run=args.dry_run)
        except Exception as e:
            r = {"slug": md.stem, "status": "error", "error": str(e)}
        results.append(r)

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    summary = {
        "total": len(results),
        "by_status": by_status,
        "by_ats": {},
        "unresolved": [],
    }
    for r in results:
        if r.get("ats"):
            summary["by_ats"][r["ats"]] = summary["by_ats"].get(r["ats"], 0) + 1
        if r.get("status") in {"unresolved", "no-careers-url", "error"}:
            summary["unresolved"].append({"slug": r["slug"], "status": r["status"], "error": r.get("error")})

    print(json.dumps({"summary": summary, "results": results}, indent=2))

    if args.report:
        Path(args.report).write_text(json.dumps({"summary": summary, "results": results}, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
