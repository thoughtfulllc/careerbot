"""Shared utilities for ATS adapters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15 careerbot/1.0"
)


class AdapterError(Exception):
    pass


def http_get_json(url: str, timeout: int = 20, extra_headers: Optional[dict] = None) -> dict:
    """GET a URL and return parsed JSON. Raises AdapterError on any failure."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AdapterError(f"HTTP {e.code} from {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise AdapterError(f"URL error fetching {url}: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise AdapterError(f"Bad JSON from {url}: {e}") from e
    except Exception as e:  # timeout, etc.
        raise AdapterError(f"Failed to fetch {url}: {e}") from e


def http_post_json(url: str, body: dict, timeout: int = 20, extra_headers: Optional[dict] = None) -> dict:
    """POST JSON body and return parsed JSON. Raises AdapterError on any failure."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AdapterError(f"HTTP {e.code} from POST {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise AdapterError(f"URL error POST {url}: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise AdapterError(f"Bad JSON from POST {url}: {e}") from e
    except Exception as e:
        raise AdapterError(f"Failed to POST {url}: {e}") from e


def http_get_text(url: str, timeout: int = 20) -> str:
    """GET a URL and return raw text. Used by the custom HTML adapter."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise AdapterError(f"HTTP {e.code} from {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise AdapterError(f"URL error fetching {url}: {e.reason}") from e
    except Exception as e:
        raise AdapterError(f"Failed to fetch {url}: {e}") from e


def truncate_excerpt(text: str, n: int = 500) -> str:
    if not text:
        return ""
    t = " ".join(text.split())  # collapse whitespace
    return t[:n] + ("..." if len(t) > n else "")
