"""Cached TMDB access that degrades gracefully when the network is blocked.

Every response is written to `tmdb_cache.pkl` on disk, so posters, trailers and
watch links keep working offline (and on repeat visits) even if the TMDB host is
unreachable -- which is common on locked-down or region-restricted networks.

No API key is needed to *display* images. `poster_path` values are stored in the
cache, and `https://image.tmdb.org/t/p/w500/<poster_path>` is public.
"""

from __future__ import annotations

import os
import pickle
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = (os.getenv("TMDB_API_KEY") or "").strip()
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_LANG = os.getenv("TMDB_LANG", "en-US")
CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tmdb_cache.pkl"
)

CACHE_TTL_SECONDS = int(os.getenv("TMDB_CACHE_TTL_DAYS", "30")) * 86400
PROBE_TTL_SECONDS = 300
SAVE_EVERY = 25
TIMEOUT_SECONDS = 12.0

# Escape hatch for networks that TLS-intercept outbound HTTPS (some corporate
# proxies and antivirus suites). It disables certificate verification, so keep it
# local-only and off on any shared deployment.
INSECURE_SSL = (os.getenv("TMDB_INSECURE_SSL") or "").lower() in {"1", "true", "yes"}

_NO_POSTER_PLACEHOLDER = "https://image.tmdb.org/t/p/w500"


def _is_youtube(video: Dict[str, Any]) -> bool:
    """TMDB reports the site as "YouTube" (sometimes a full host), and the
    casing varies, so match on a lowercase prefix."""
    return str(video.get("site", "")).lower().startswith("youtube")


class TMDBUnavailable(RuntimeError):
    """Raised when TMDB cannot be reached at all (network block, bad key, ...)."""


def is_configured() -> bool:
    return bool(TMDB_API_KEY)


class TMDBCache:
    """Timestamped key -> value store, persisted to a pickle file."""

    def __init__(self, path: str = CACHE_PATH, ttl: int = CACHE_TTL_SECONDS) -> None:
        self.path = path
        self.ttl = ttl
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._pending = 0
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, "rb") as fh:
                data = pickle.load(fh)
        except (FileNotFoundError, EOFError, AttributeError, ImportError,
                pickle.UnpicklingError):
            self._data = {}
            return
        if isinstance(data, dict):
            self._data = {
                k: v
                for k, v in data.items()
                if isinstance(v, tuple) and len(v) == 2
            }

    def lookup(self, key: str) -> Tuple[bool, Any, bool]:
        """Return (found, value, fresh). `found` distinguishes a cached miss."""
        hit = self._data.get(key)
        if hit is None:
            return False, None, False
        stamp, value = hit
        return True, value, (time.time() - stamp) <= self.ttl

    def put(self, key: str, value: Any, *, force: bool = False) -> None:
        self._data[key] = (time.time(), value)
        self._pending += 1
        if force or self._pending >= SAVE_EVERY:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        try:
            tmp = f"{self.path}.tmp"
            with open(tmp, "wb") as fh:
                pickle.dump(self._data, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, self.path)  # atomic: never leaves a half-written cache
            self._pending = 0
        except OSError:
            pass  # a read-only deployment dir just means no persistence

    def drop(self, key: str) -> None:
        if self._data.pop(key, None) is not None:
            self._pending += 1
            self.flush()

    def clear(self) -> None:
        self._data.clear()
        self._pending = 1
        self.flush()

    def stats(self) -> Dict[str, int]:
        now = time.time()
        return {
            "total": len(self._data),
            "fresh": sum(1 for s, _ in self._data.values() if now - s <= self.ttl),
        }


_cache: Optional[TMDBCache] = None


def get_cache() -> TMDBCache:
    global _cache
    if _cache is None:
        _cache = TMDBCache()
    return _cache


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
        verify=not INSECURE_SSL,
        headers={"Accept": "application/json"},
    )


def _request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not is_configured():
        raise TMDBUnavailable("TMDB_API_KEY is not set (check your .env file).")
    query = {"api_key": TMDB_API_KEY, "language": TMDB_LANG, **params}
    try:
        response = _client().get(f"{TMDB_BASE}{path}", params=query)
    except httpx.RequestError as exc:
        raise TMDBUnavailable(
            f"Could not reach TMDB ({type(exc).__name__}). "
            "The host may be blocked on this network."
        ) from exc
    if response.status_code == 401:
        raise TMDBUnavailable("TMDB rejected the API key (401).")
    if response.status_code == 429:
        raise TMDBUnavailable("TMDB rate limit hit (429); try again shortly.")
    if response.status_code != 200:
        raise TMDBUnavailable(f"TMDB returned HTTP {response.status_code}.")
    return response.json()


def probe() -> Tuple[bool, str]:
    """(reachable, message), memoized briefly so we never hammer a dead host.

    The message is cached alongside the verdict: a cached failure still has to
    explain itself, otherwise the UI shows a warning with no reason.
    """
    cache = get_cache()
    found, value, fresh = cache.lookup("__probe__")
    if found and fresh:
        reachable, message = value
        return bool(reachable), str(message or "")
    if not is_configured():
        reason = "TMDB_API_KEY is not set. Posters are disabled."
        cache.put("__probe__", (False, reason), force=True)
        return False, reason
    try:
        _request("/configuration", {})
    except TMDBUnavailable as exc:
        reason = str(exc)
        cache.put("__probe__", (False, reason), force=True)
        return False, reason
    cache.put("__probe__", (True, ""), force=True)
    return True, ""


def _cached(key: str, loader) -> Tuple[Any, bool]:
    """Return (value, from_cache) using the disk cache as a memo layer."""
    cache = get_cache()
    found, value, fresh = cache.lookup(key)
    if found and fresh:
        return value, True
    value = loader()
    cache.put(key, value, force=True)
    return value, False


def poster_url(path: Optional[str], size: str = "w500") -> Optional[str]:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def _pick_trailer(videos: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Prefer an official English YouTube trailer, then relax each constraint."""
    results = videos.get("results") or []
    youtube = [v for v in results if _is_youtube(v) and v.get("key")]

    def rank(video: Dict[str, Any]) -> tuple:
        return (
            video.get("type") == "Trailer",
            bool(video.get("official")),
            video.get("published_at") or "",
        )

    for pool, tag in (
        ([v for v in youtube if v.get("type") == "Trailer" and v.get("official")],
         "official"),
        ([v for v in youtube if v.get("type") == "Trailer"], "trailer"),
        (youtube, "video"),
    ):
        if pool:
            best = max(pool, key=rank)
            return {
                "key": best["key"],
                "name": best.get("name") or best.get("title") or tag,
                "site": best.get("site") or "YouTube",
                "type": best.get("type") or tag,
            }
    return None


_OFFER_ORDER = (
    ("flatrate", "Stream"),
    ("rent", "Rent"),
    ("buy", "Buy"),
    ("ads", "Free with ads"),
)


def _pick_providers(payload: Dict[str, Any], region: str) -> List[Dict[str, str]]:
    """Flatten JustWatch provider data for one region into simple dicts."""
    results = payload.get("results") or {}
    country = results.get(region) or results.get("US") or {}
    out: List[Dict[str, str]] = []
    for offer, label in _OFFER_ORDER:
        for entry in country.get(offer) or []:
            out.append(
                {
                    "name": entry.get("provider_name") or "",
                    "offer": label,
                    "logo_url": poster_url(entry.get("logo_path"), "w92") or "",
                    # Deep link to the provider's watch page (JustWatch data).
                    "link": entry.get("link") or country.get("link") or "",
                }
            )
    seen, unique = set(), []
    for entry in out:
        key = (entry["name"], entry["offer"])
        if entry["name"] and key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def search_movie(title: str) -> Optional[Dict[str, Any]]:
    """Resolve a title to a TMDB movie card (poster included), or None.

    Prefers results that actually have artwork, since a poster-less match is
    usually a different film with the same name.
    """
    from movies import normalize_title  # local import: avoids a cycle at import time

    key = f"search:{normalize_title(title)}"

    def loader() -> Optional[Dict[str, Any]]:
        payload = _request(
            "/search/movie",
            {"query": str(title), "include_adult": "false", "page": 1},
        )
        results = payload.get("results") or []
        if not results:
            return None
        wanted = normalize_title(title)
        exact = [
            m for m in results
            if normalize_title(m.get("title") or m.get("original_title") or "")
            == wanted
        ]
        pool = exact or results
        best = next((m for m in pool if m.get("poster_path")), pool[0])
        return _card(best)

    value, _ = _cached(key, loader)
    return value


def _card(movie: Dict[str, Any]) -> Dict[str, Any]:
    release = movie.get("release_date") or ""
    return {
        "tmdb_id": int(movie["id"]),
        "title": movie.get("title") or movie.get("original_title") or "",
        "original_title": movie.get("original_title"),
        "overview": movie.get("overview") or None,
        "tagline": movie.get("tagline") or None,
        "release_date": release or None,
        "year": int(release[:4]) if release[:4].isdigit() else None,
        "runtime": movie.get("runtime"),
        "vote_average": movie.get("vote_average"),
        "vote_count": movie.get("vote_count"),
        "poster_url": poster_url(movie.get("poster_path")),
        "backdrop_url": poster_url(movie.get("backdrop_path"), "w780"),
        "genres": [g["name"] for g in movie.get("genres") or []],
        "homepage": movie.get("homepage") or None,
        "imdb_id": movie.get("imdb_id") or None,
    }


def movie_details(tmdb_id: int, region: str = "US") -> Dict[str, Any]:
    """Full record for one movie: artwork, trailer and watch providers.

    Everything comes from a single request via `append_to_response`, so opening
    a movie costs one call rather than three.
    """
    key = f"details:{int(tmdb_id)}:{region}"

    def loader() -> Dict[str, Any]:
        payload = _request(
            f"/movie/{int(tmdb_id)}",
            {"append_to_response": "videos,watch/providers"},
        )
        card = _card(payload)
        card["trailer"] = _pick_trailer(payload.get("videos") or {})
        card["providers"] = _pick_providers(
            payload.get("watch/providers") or {}, region
        )
        return card

    value, _ = _cached(key, loader)
    return value


def resolve(title: str, region: str = "US") -> Optional[Dict[str, Any]]:
    """Title -> full movie record, or None if TMDB has no match.

    Combines `search_movie` and `movie_details` so callers get artwork, trailer
    and watch links from one call.
    """
    card = search_movie(title)
    if not card:
        return None
    return movie_details(card["tmdb_id"], region=region)
