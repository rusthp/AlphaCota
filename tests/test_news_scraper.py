"""Tests for data/news_scraper.py — Multi-source RSS news scraper."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data.news_scraper as scraper


def _make_entry(title="HGLG11 sobe 3%", published="2025-03-01", link="https://example.com/news", summary=""):
    """Helper to create a mock RSS entry."""
    entry = MagicMock()
    entry.title = title
    entry.published = published
    entry.link = link
    entry.summary = summary
    entry.get = lambda k, d="": {"title": title, "published": published, "link": link, "summary": summary}.get(k, d)
    return entry


def _make_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


class TestFetchFiiNews:
    def test_returns_list_with_fonte(self):
        """News items should include 'fonte' field from multi-source scraper."""
        entries = [_make_entry(), _make_entry(title="HGLG11 cai 2%")]
        mock_feed = _make_feed(entries)

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.return_value = mock_feed
            result = scraper.fetch_fii_news("HGLG11", max_results=5)
            assert len(result) >= 1
            assert "titulo" in result[0]
            assert "fonte" in result[0]
            assert "data" in result[0]
            assert "link" in result[0]

    def test_no_feedparser_returns_empty(self):
        with patch.object(scraper, "HAS_FEEDPARSER", False):
            result = scraper.fetch_fii_news("HGLG11")
            assert result == []

    def test_deduplication(self):
        """Duplicate titles should be removed."""
        entries = [
            _make_entry(title="HGLG11 sobe 3%"),
            _make_entry(title="HGLG11 sobe 3%"),
            _make_entry(title="HGLG11 cai 1%"),
        ]
        result = scraper._deduplicate_news(
            [
                {"titulo": "HGLG11 sobe 3%", "data": "d", "link": "l", "fonte": "A"},
                {"titulo": "HGLG11 sobe 3%", "data": "d", "link": "l", "fonte": "B"},
                {"titulo": "HGLG11 cai 1%", "data": "d", "link": "l", "fonte": "C"},
            ]
        )
        assert len(result) == 2

    def test_max_results_limits_output(self):
        entries = [_make_entry(title=f"News {i}") for i in range(20)]
        mock_feed = _make_feed(entries)

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.return_value = mock_feed
            result = scraper.fetch_fii_news("XPML11", max_results=3)
            assert len(result) <= 3

    def test_empty_feed(self):
        mock_feed = _make_feed([])

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.return_value = mock_feed
            result = scraper.fetch_fii_news("HGLG11")
            assert result == []

    def test_default_max_results_is_10(self):
        """Default max_results changed from 5 to 10."""
        entries = [_make_entry(title=f"Unique news {i}") for i in range(15)]
        mock_feed = _make_feed(entries)

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.return_value = mock_feed
            result = scraper.fetch_fii_news("MXRF11")
            assert len(result) <= 10


class TestFetchMarketNews:
    def test_returns_list(self):
        entries = [_make_entry(title="FIIs sobem com queda da Selic")]
        mock_feed = _make_feed(entries)

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.return_value = mock_feed
            result = scraper.fetch_market_news(max_results=5)
            assert isinstance(result, list)

    def test_no_feedparser_returns_empty(self):
        with patch.object(scraper, "HAS_FEEDPARSER", False):
            result = scraper.fetch_market_news()
            assert result == []


class TestEntryMatchTicker:
    def test_matches_in_title(self):
        entry = _make_entry(title="HGLG11 sobe 3% hoje")
        assert scraper._entry_matches_ticker(entry, "HGLG11") is True

    def test_no_match(self):
        entry = _make_entry(title="Selic cai para 10%")
        assert scraper._entry_matches_ticker(entry, "HGLG11") is False

    def test_matches_in_summary(self):
        entry = _make_entry(title="FIIs sobem", summary="O fundo HGLG11 teve alta de 3%")
        assert scraper._entry_matches_ticker(entry, "HGLG11") is True


class TestEntryMatchKeywords:
    def test_empty_keywords_matches_all(self):
        entry = _make_entry(title="Qualquer coisa")
        assert scraper._entry_matches_keywords(entry, []) is True

    def test_matches_keyword(self):
        entry = _make_entry(title="FII HGLG11 paga dividendo recorde")
        assert scraper._entry_matches_keywords(entry, ["fii", "dividendo"]) is True

    def test_no_match(self):
        entry = _make_entry(title="Bitcoin atinge nova máxima")
        assert scraper._entry_matches_keywords(entry, ["fii", "dividendo"]) is False


class TestListSources:
    def test_returns_sources_with_type(self):
        sources = scraper.list_sources()
        assert len(sources) > 0
        for s in sources:
            assert "name" in s
            assert s["type"] in ("ticker", "general")

    def test_has_ticker_and_general_sources(self):
        sources = scraper.list_sources()
        types = {s["type"] for s in sources}
        assert "ticker" in types
        assert "general" in types


class TestFetchFiiNewsExceptions:
    def test_ticker_source_exception_handled(self):
        """When a ticker RSS source raises, it should be caught gracefully."""

        def bad_parse(url, **kwargs):
            if "search" in url:
                raise RuntimeError("Network failure")
            return _make_feed([])

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.side_effect = bad_parse
            result = scraper.fetch_fii_news("HGLG11", max_results=5)
            assert isinstance(result, list)

    def test_general_source_exception_handled(self):
        """When a general RSS source raises, it should be caught gracefully."""
        call_count = 0

        def partial_fail(url, **kwargs):
            nonlocal call_count
            call_count += 1
            # First few calls (ticker sources) work, then general sources fail
            if call_count > 2:
                raise RuntimeError("Feed unavailable")
            return _make_feed([_make_entry(title=f"HGLG11 news {call_count}")])

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.side_effect = partial_fail
            result = scraper.fetch_fii_news("HGLG11", max_results=10)
            assert isinstance(result, list)


class TestFetchMarketNewsExceptions:
    def test_google_news_exception_handled(self):
        """When Google News RSS raises, market news should still return results."""
        call_count = 0

        def partial_fail(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Google News down")
            return _make_feed([_make_entry(title="FII news")])

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.side_effect = partial_fail
            result = scraper.fetch_market_news(max_results=5)
            assert isinstance(result, list)

    def test_general_source_exception_handled(self):
        """When a general RSS source raises in market news, it should be caught."""
        call_count = 0

        def partial_fail(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise RuntimeError("Feed timeout")
            return _make_feed([_make_entry(title="Market news")])

        with patch.object(scraper, "HAS_FEEDPARSER", True), patch.object(scraper, "feedparser") as mock_fp:
            mock_fp.parse.side_effect = partial_fail
            result = scraper.fetch_market_news(max_results=5)
            assert isinstance(result, list)


class TestParseDate:
    def test_published_field(self):
        entry = _make_entry(published="Mon, 01 Mar 2025 12:00:00 GMT")
        result = scraper._parse_date(entry)
        assert "2025" in result

    def test_fallback_to_now(self):
        entry = MagicMock()
        entry.published = None
        entry.updated = None
        entry.created = None
        entry.get = lambda k, d=None: None
        result = scraper._parse_date(entry)
        assert len(result) > 0  # Should return current datetime
