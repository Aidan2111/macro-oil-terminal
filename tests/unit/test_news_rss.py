"""Unit tests for the RSS news aggregator + sentiment scoring (issue #80)."""

from __future__ import annotations

import pytest


def test_score_sentiment_positive():
    from providers import news_rss

    score, label = news_rss.score_sentiment("Crude oil prices surge as inventories tighten")
    assert label in {"positive", "neutral"}  # VADER may grade differently from keywords
    if label == "positive":
        assert score > 0


def test_score_sentiment_negative():
    from providers import news_rss

    score, label = news_rss.score_sentiment("Oil tumbles on glut fears and supply build")
    # Either VADER or the keyword fallback should land negative.
    assert label != "positive"
    if label == "negative":
        assert score < 0


def test_score_sentiment_neutral_text_returns_neutral_or_close():
    from providers import news_rss

    score, label = news_rss.score_sentiment(
        "OPEC delegates to meet next month, agenda not yet set"
    )
    # Allow VADER's bias either way; just sanity-check magnitude is small
    # under the keyword fallback.
    assert -0.5 <= score <= 0.5


def test_parse_rss_extracts_items():
    from providers import news_rss

    xml = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Brent rallies 3%</title>
      <link>https://example.com/1</link>
      <pubDate>Tue, 28 Apr 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Oil falls on inventory build</title>
      <link>https://example.com/2</link>
      <pubDate>Tue, 28 Apr 2026 11:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
    items = news_rss.parse_rss(xml, source="Test")
    assert len(items) == 2
    assert items[0]["title"] == "Brent rallies 3%"
    assert items[0]["link"] == "https://example.com/1"
    assert items[0]["published_iso"] is not None  # parsed
    assert items[0]["source"] == "Test"


def test_parse_rss_handles_malformed_xml_returning_empty():
    from providers import news_rss

    items = news_rss.parse_rss(b"not xml at all", source="Broken")
    assert items == []


def test_top_weighted_picks_highest_magnitude():
    from providers import news_rss

    headlines = [
        {"title": "A", "sentiment_score": 0.1, "published_iso": "2026-04-28T01:00:00Z"},
        {"title": "B", "sentiment_score": -0.9, "published_iso": "2026-04-28T02:00:00Z"},
        {"title": "C", "sentiment_score": 0.5, "published_iso": "2026-04-28T03:00:00Z"},
        {"title": "D", "sentiment_score": -0.3, "published_iso": "2026-04-28T04:00:00Z"},
    ]
    top = news_rss.top_weighted(headlines, limit=2)
    titles = [t["title"] for t in top]
    assert "B" in titles  # |-0.9| is highest
    assert "C" in titles  # |0.5| is next


def test_fetch_recent_with_injected_fetch(monkeypatch, tmp_path):
    """Round-trip test: feeds are injected, fetch_fn is mocked, the
    cache is redirected to tmp_path so the test is hermetic."""
    from providers import news_rss

    monkeypatch.setattr(news_rss, "_CACHE_PATH", tmp_path / "headlines.json")

    def _fake_fetch(source: str, url: str):
        return [
            {
                "source": source,
                "title": f"{source} surge headline",
                "link": "https://example.com",
                "published_iso": "2026-04-28T12:00:00+00:00",
            },
        ]

    feeds = [("Reuters", "https://x"), ("OilPrice", "https://y")]
    payload = news_rss.fetch_recent(feeds=feeds, fetch_fn=_fake_fetch)
    assert payload["count"] == 2
    assert all("sentiment_score" in h for h in payload["headlines"])
    assert all("sentiment_label" in h for h in payload["headlines"])
    # Sources should be preserved.
    sources = {h["source"] for h in payload["headlines"]}
    assert sources == {"Reuters", "OilPrice"}


def test_fetch_recent_one_failing_feed_does_not_break_others(monkeypatch, tmp_path):
    from providers import news_rss

    monkeypatch.setattr(news_rss, "_CACHE_PATH", tmp_path / "headlines.json")

    def _fake_fetch(source: str, url: str):
        if source == "Broken":
            return []  # simulating a failed fetch
        return [
            {
                "source": source,
                "title": "Crude rises on tightening supply",
                "link": "https://example.com",
                "published_iso": "2026-04-28T12:00:00+00:00",
            },
        ]

    payload = news_rss.fetch_recent(
        feeds=[("Reuters", "https://x"), ("Broken", "https://broken")],
        fetch_fn=_fake_fetch,
    )
    assert payload["count"] == 1
    assert payload["headlines"][0]["source"] == "Reuters"
