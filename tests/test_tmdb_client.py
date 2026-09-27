"""Tests for TMDB response parsing and cache behaviour.

These run entirely offline: `tmdb_get` is stubbed, so no network is needed and
no API key is required.

Run with:  python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tmdb_client as tmdb
from movies import normalize_title


# ------------------------------------------------------------------- trailers
def _video(key, site="YouTube", kind="Trailer", official=True, published="2020-01-01"):
    return {
        "key": key, "site": site, "type": kind, "official": official,
        "published_at": published, "name": f"{key} name",
    }


def test_prefers_official_trailer():
    payload = {"results": [
        _video("teaser", kind="Teaser", official=False),
        _video("official", kind="Trailer", official=True, published="2024-01-01"),
        _video("fan", kind="Trailer", official=False, published="2025-01-01"),
    ]}
    assert tmdb._pick_trailer(payload)["key"] == "official"


def test_youtube_site_name_is_matched_case_insensitively():
    """TMDB sends "YouTube", not "youtube.com" -- a case-sensitive check misses it."""
    assert tmdb._pick_trailer({"results": [_video("k", site="YouTube")]})["key"] == "k"
    assert tmdb._pick_trailer({"results": [_video("k", site="youtube.com")]})["key"] == "k"


def test_newest_official_trailer_wins():
    payload = {"results": [
        _video("old", published="2010-01-01"),
        _video("new", published="2024-01-01"),
    ]}
    assert tmdb._pick_trailer(payload)["key"] == "new"


def test_falls_back_when_no_official_trailer():
    payload = {"results": [
        _video("teaser", kind="Teaser", official=False),
        _video("plain", kind="Trailer", official=False),
    ]}
    assert tmdb._pick_trailer(payload)["key"] == "plain"


@pytest.mark.parametrize("payload", [
    {},
    {"results": []},
    {"results": [_video("v", site="Vimeo")]},
    {"results": [{"key": "", "site": "YouTube", "type": "Trailer"}]},
])
def test_no_usable_trailer_returns_none(payload):
    assert tmdb._pick_trailer(payload) is None


# ------------------------------------------------------------------ providers
WATCH_PAYLOAD = {"results": {"US": {
    "link": "https://example.test/watch",
    "flatrate": [{"provider_name": "Netflix", "logo_path": "/n.png"}],
    "rent": [{"provider_name": "Apple TV", "logo_path": "/a.png"}],
    "buy": [{"provider_name": "Amazon Video", "logo_path": "/z.png"}],
}}}


def test_providers_are_ordered_streaming_first():
    offers = [p["offer"] for p in tmdb._pick_providers(WATCH_PAYLOAD, "US")]
    assert offers == ["Stream", "Rent", "Buy"]


def test_provider_logo_urls_are_absolute():
    provider = tmdb._pick_providers(WATCH_PAYLOAD, "US")[0]
    assert provider["logo_url"].startswith("https://image.tmdb.org/t/p/w92/")


def test_unknown_region_falls_back_to_us():
    assert [p["name"] for p in tmdb._pick_providers(WATCH_PAYLOAD, "GB")] == [
        "Netflix", "Apple TV", "Amazon Video"
    ]


def test_no_providers_returns_empty_list():
    assert tmdb._pick_providers({"results": {}}, "US") == []
    assert tmdb._pick_providers({}, "US") == []


# ------------------------------------------------------------- image helpers
def test_poster_url():
    assert tmdb.poster_url("/abc.jpg") == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert tmdb.poster_url("/abc.jpg", "w92").endswith("/w92/abc.jpg")
    assert tmdb.poster_url(None) is None
    assert tmdb.poster_url("") is None


# ---------------------------------------------------------------------- cache
@pytest.fixture
def cache(tmp_path, monkeypatch):
    """An isolated cache, also installed as the module-level singleton.

    Isolating the file keeps tests from sharing state, and redirecting the
    singleton stops a test from writing to the repo's real tmdb_cache.pkl.
    """
    monkeypatch.setattr(tmdb, "_cache", None)
    store = tmdb.TMDBCache(path=str(tmp_path / "tmdb_cache.pkl"))
    monkeypatch.setattr(tmdb, "_cache", store)
    return store


def test_cache_round_trips_to_disk(cache, tmp_path):
    cache.put("k", {"title": "Inception"}, force=True)
    reloaded = tmdb.TMDBCache(path=str(tmp_path / "tmdb_cache.pkl"))
    found, value, fresh = reloaded.lookup("k")
    assert found and value == {"title": "Inception"} and fresh


def test_cache_distinguishes_miss_from_cached_none(cache):
    """A title absent from TMDB must be remembered as "no match"."""
    cache.put("search:ghost", None, force=True)
    found, value, _ = cache.lookup("search:ghost")
    assert found and value is None
    assert cache.lookup("never-stored")[0] is False


def test_cache_entries_expire(tmp_path, monkeypatch):
    monkeypatch.setattr(tmdb, "_cache", None)  # do not install this one globally
    stale = tmdb.TMDBCache(path=str(tmp_path / "c.pkl"), ttl=-1)
    stale.put("k", 1, force=True)
    assert stale.lookup("k")[2] is False, "expired entries must not count as fresh"


def test_cache_flush_writes_atomically(cache, tmp_path):
    cache.put("a", 1)
    cache.flush()
    assert (tmp_path / "tmdb_cache.pkl").exists()
    assert not list(tmp_path.glob("*.tmp")), "temp file should be renamed away"


def test_cache_tolerates_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tmdb, "_cache", None)  # do not install this one globally
    path = tmp_path / "broken.pkl"
    path.write_bytes(b"not a pickle at all")
    recovered = tmdb.TMDBCache(path=str(path))
    assert recovered.lookup("anything")[0] is False


# ------------------------------------------------------------- search + cards
def test_search_prefers_exact_title_match(monkeypatch, cache):
    seen = {}

    def fake_get(path, params):
        seen["query"] = params["query"]
        return {"results": [
            {"id": 1, "title": "The Avengers:something", "poster_path": "/a.jpg"},
            {"id": 2, "title": "The Avengers", "poster_path": "/b.jpg"},
        ]}

    monkeypatch.setattr(tmdb, "_request", fake_get)
    assert tmdb.search_movie("the avengers")["tmdb_id"] == 2


def test_search_prefers_a_result_that_has_a_poster(monkeypatch, cache):
    monkeypatch.setattr(tmdb, "_request", lambda p, q: {"results": [
        {"id": 1, "title": "Some Movie"},
        {"id": 2, "title": "Some Movie", "poster_path": "/b.jpg"},
    ]})
    assert tmdb.search_movie("some movie")["tmdb_id"] == 2


def test_search_returns_none_when_tmdb_has_no_match(monkeypatch, cache):
    monkeypatch.setattr(tmdb, "_request", lambda p, q: {"results": []})
    assert tmdb.search_movie("a movie that does not exist") is None


def test_search_is_cached_across_calls(cache, monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append(path)
        return {"results": [{"id": 7, "title": "Cached", "poster_path": "/c.jpg"}]}

    monkeypatch.setattr(tmdb, "_request", fake_get)
    first = tmdb.search_movie("cached")
    second = tmdb.search_movie("Cached")  # different case, same normalized key
    assert first == second
    assert calls == ["/search/movie"], "second call should be served from cache"


def test_card_parses_release_year(monkeypatch, cache):
    monkeypatch.setattr(tmdb, "_request", lambda p, q: {"results": [
        {"id": 5, "title": "Dated", "release_date": "1999-12-31", "poster_path": "/d.jpg"},
    ]})
    assert tmdb.search_movie("dated")["year"] == 1999


def test_card_handles_a_missing_release_date(monkeypatch, cache):
    monkeypatch.setattr(tmdb, "_request", lambda p, q: {"results": [
        {"id": 6, "title": "Undated", "release_date": ""},
    ]})
    card = tmdb.search_movie("undated")
    assert card["year"] is None and card["poster_url"] is None


# ----------------------------------------------------------------- resilience
def test_unavailable_raises_a_clear_error(monkeypatch, cache):
    import httpx

    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "x" * 32)

    def boom(*args, **kwargs):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(tmdb, "_client", boom)
    with pytest.raises(tmdb.TMDBUnavailable) as exc:
        tmdb._request("/movie/1", {})
    assert "TMDB" in str(exc.value)


def test_probe_reports_failure_without_raising(monkeypatch, cache):
    import httpx

    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "x" * 32)

    def boom(*args, **kwargs):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(tmdb, "_client", boom)
    reachable, message = tmdb.probe()
    assert reachable is False and message


def test_probe_reports_missing_key(cache, monkeypatch):
    """The key check must come before any network call, and say which var is wrong."""
    import httpx

    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "")

    def boom(*args, **kwargs):
        raise AssertionError("must not hit the network without an API key")

    monkeypatch.setattr(tmdb, "_request", boom)
    reachable, message = tmdb.probe()
    assert reachable is False and "TMDB_API_KEY" in message


def test_probe_keeps_its_message_on_a_cached_failure(cache, monkeypatch):
    """A cached negative must still explain itself on later runs."""
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "")
    assert tmdb.probe()[1] != ""
    assert tmdb.probe()[1] != "", "second call came from cache"


def test_network_failure_does_not_poison_the_cache(monkeypatch, cache):
    """A blocked host must not be cached as 'this title has no match'."""
    import httpx

    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "x" * 32)

    def boom(*args, **kwargs):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(tmdb, "_client", boom)
    with pytest.raises(tmdb.TMDBUnavailable):
        tmdb.search_movie("inception")
    assert cache.lookup(f"search:{normalize_title('inception')}")[0] is False
