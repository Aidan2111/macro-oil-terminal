"""RSS news aggregator for oil-market headlines (issue #80).

Pulls headlines from a small set of free RSS feeds, normalises the
timestamp + title, scores VADER sentiment (no external API call), and
caches the result on disk for 15 minutes. The endpoint
`/api/news/headlines` is the consumer.

Defensive against feed failures: any single feed that errors is
logged and skipped — the others still flow.

Sentiment is via `vaderSentiment` if installed, else a degraded
keyword-based scorer (so the unit tests don't require the package).
"""

from __future__ import annotations

import json
import logging
import pathlib
import threading
import time as _time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


# --- Feed registry ----------------------------------------------------------

# (source label, url). Trim / extend per ops feedback. Each feed is
# fetched independently with a short timeout.
DEFAULT_FEEDS: list[tuple[str, str]] = [
    ("Reuters Energy", "https://www.reuters.com/business/energy/rss/"),
    ("OilPrice", "https://oilprice.com/rss/main"),
    ("Argus", "https://www.argusmedia.com/en/rss-feeds/news"),
]


# --- Sentiment --------------------------------------------------------------

_POS_TOKENS = (
    "rally", "surge", "jump", "soar", "gain", "rise", "rises", "climb", "climbs",
    "bull", "tighten", "tightens", "draws", "draw down", "shortage", "outage",
    "boost",
)
_NEG_TOKENS = (
    "plunge", "tumble", "fall", "falls", "drop", "drops", "slump", "slip",
    "bear", "glut", "supply build", "build", "sanctions ease", "release",
    "ceasefire",
)


def _keyword_sentiment(text: str) -> float:
    """Tiny keyword-based fallback. Returns a score in [-1, 1]."""
    s = text.lower()
    pos = sum(1 for tok in _POS_TOKENS if tok in s)
    neg = sum(1 for tok in _NEG_TOKENS if tok in s)
    if pos == 0 and neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(1, pos + neg)))


def _vader_sentiment(text: str) -> Optional[float]:
    """Try VADER. Returns None if the package isn't available."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore
    except Exception:
        return None
    try:
        return float(SentimentIntensityAnalyzer().polarity_scores(text)["compound"])
    except Exception:
        return None


def score_sentiment(text: str) -> tuple[float, str]:
    """Return ``(score, label)`` where label ∈ {"positive", "neutral", "negative"}.

    Prefers VADER if installed; falls back to the keyword bag.
    """
    score = _vader_sentiment(text)
    if score is None:
        score = _keyword_sentiment(text)
    if score >= 0.05:
        return score, "positive"
    if score <= -0.05:
        return score, "negative"
    return score, "neutral"


# --- RSS parsing ------------------------------------------------------------

_RSS_FIELDS = ("item",)
_RSS_TIMEOUT = 8.0  # seconds per feed


def _http_get(url: str, *, timeout: float = _RSS_TIMEOUT) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "macro-oil-terminal/news-rss"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_rfc822(when: Optional[str]) -> Optional[str]:
    """Coerce a feed's <pubDate> string to ISO 8601 UTC; return None on failure."""
    if not when:
        return None
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(when)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_rss(xml_bytes: bytes, source: str) -> list[dict[str, Any]]:
    """Parse RSS 2.0 / Atom-ish XML into normalised dicts.

    Returns a list of `{source, title, link, published_iso}`.
    """
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.debug("RSS parse error for %s: %r", source, exc)
        return out

    # RSS 2.0: <rss><channel><item>...
    items = root.findall(".//item")
    if not items:
        # Atom: <feed><entry>...
        items = root.findall("{http://www.w3.org/2005/Atom}entry")
    def _first(elem, *paths):
        # ElementTree elements are falsy when they have no children, so
        # `or` doesn't compose them safely — walk the path list explicitly.
        for p in paths:
            found = elem.find(p)
            if found is not None:
                return found
        return None

    for it in items:
        title_el = _first(it, "title", "{http://www.w3.org/2005/Atom}title")
        link_el = _first(it, "link", "{http://www.w3.org/2005/Atom}link")
        pub_el = _first(
            it,
            "pubDate",
            "{http://www.w3.org/2005/Atom}updated",
            "{http://www.w3.org/2005/Atom}published",
        )
        title = (title_el.text or "").strip() if title_el is not None else ""
        # Atom links are in the `href` attribute; RSS links are in element text.
        link = ""
        if link_el is not None:
            link = (link_el.text or link_el.get("href") or "").strip()
        published_iso = _parse_rfc822(pub_el.text if pub_el is not None else None)
        if not title:
            continue
        out.append(
            {
                "source": source,
                "title": title,
                "link": link,
                "published_iso": published_iso,
            }
        )
    return out


def fetch_feed(source: str, url: str) -> list[dict[str, Any]]:
    """Fetch + parse a single feed. Returns [] on any error."""
    try:
        body = _http_get(url)
    except Exception as exc:
        logger.debug("RSS fetch failed for %s (%s): %r", source, url, exc)
        return []
    return parse_rss(body, source)


# --- Cache ------------------------------------------------------------------

_CACHE_PATH = pathlib.Path("data/news/headlines.json")
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_S = 15 * 60  # 15 minutes


def _read_cache() -> Optional[dict[str, Any]]:
    if not _CACHE_PATH.exists():
        return None
    try:
        return json.loads(_CACHE_PATH.read_text())
    except Exception:
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(payload))


def fetch_recent(
    *,
    feeds: Optional[list[tuple[str, str]]] = None,
    fetch_fn=None,
) -> dict[str, Any]:
    """Fetch + score all feeds, cached 15 min on disk.

    `feeds` and `fetch_fn` are injectable for tests. Returns
    ``{generated_at, count, headlines: [...]}`` with each headline
    augmented with a ``sentiment_score`` and ``sentiment_label``.
    """
    feeds = feeds or DEFAULT_FEEDS
    fetch_fn = fetch_fn or fetch_feed

    now = _time.time()
    with _CACHE_LOCK:
        cached = _read_cache()
        if cached is not None:
            ts = cached.get("_cached_at_ts", 0)
            if isinstance(ts, (int, float)) and now - ts < _CACHE_TTL_S:
                # Strip the private key before returning.
                return {k: v for k, v in cached.items() if not k.startswith("_")}

    headlines: list[dict[str, Any]] = []
    for source, url in feeds:
        for item in fetch_fn(source, url):
            text = item["title"]
            score, label = score_sentiment(text)
            item["sentiment_score"] = round(score, 4)
            item["sentiment_label"] = label
            headlines.append(item)

    headlines.sort(key=lambda h: h.get("published_iso") or "", reverse=True)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(headlines),
        "headlines": headlines,
    }
    with _CACHE_LOCK:
        _write_cache({**payload, "_cached_at_ts": now})
    return payload


def top_weighted(
    headlines: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the `limit` highest-magnitude (|sentiment_score|) headlines.

    Ties broken by recency. Used by `thesis_context` to feed the LLM
    prompt the most polarised recent items.
    """
    def _key(h: dict[str, Any]) -> tuple[float, str]:
        score = float(h.get("sentiment_score") or 0.0)
        return (abs(score), str(h.get("published_iso") or ""))

    ranked = sorted(headlines, key=_key, reverse=True)
    return [
        {
            "source": h.get("source"),
            "title": h.get("title"),
            "sentiment_score": h.get("sentiment_score"),
        }
        for h in ranked[:limit]
    ]
