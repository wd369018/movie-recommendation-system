"""Cached TMDB access that degrades gracefully when the network is blocked.

Every response is written to `tmdb_cache.pkl` on disk, so posters, trailers and
watch links keep working offline (and on repeat visits) even if the TMDB host is
unreachable -- which is common on locked-down or region-restricted networks.

No API key is needed to *display* images. `poster_path` values are stored in the
cache, and `https://image.tmdb.org/t/p/w500/<poster_path>` is public.
"""

from __future__ import annotations

import json
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

# Preferred alternative to the above: point this at a .pem/.crt holding the
# intercepting proxy's CA and verification stays ON. Sophos SSL VPN, for example,
# re-signs traffic with "Sophos SSL CA_*", which no public CA bundle contains --
# export that one certificate and set this, and the app connects normally.
CA_BUNDLE = (os.getenv("TMDB_CA_BUNDLE") or "").strip()

# ---------------------------------------------------------------------------
# Working around a network that blocks TMDB outright.
#
# Some networks (corporate gateways, some ISPs) refuse TLS to specific hosts
# instead of intercepting it, and no local setting can fix that. Two public
# services can route around it:
#
#   * RELAYS fetch the API response from a third-party host, so the request
#     never leaves through the blocked route.
#   * IMAGE_PROXY_TEMPLATE does the same for image.tmdb.org, which these
#     networks almost always block on exactly the same rule.
#
# Consequence: the relay operator can see your API key, because it travels in
# the URL. Acceptable for a local project, not for a shared or public
# deployment. Set TMDB_RELAY=off to refuse it, and rotate the key at
# https://www.themoviedb.org/settings/api if you do use it.
IMAGE_PROXY_TEMPLATE = "https://images.weserv.nl/?url={target}"
RELAY_MODE = (os.getenv("TMDB_RELAY") or "auto").strip().lower()  # auto|off|only
RELAY_TIMEOUT = 30.0


def _unwrap_jina(outer: Dict[str, Any]) -> Dict[str, Any]:
    """r.jina.ai returns {"data": {"content": "<body as a string>", ...}}."""
    data = outer.get("data")
    if isinstance(data, dict) and "content" in data:
        return _loads(data["content"])
    raise TMDBUnavailable("Relay response had no `data.content`.")


def _unwrap_allorigins(outer: Dict[str, Any]) -> Dict[str, Any]:
    """api.allorigins.win wraps the upstream body as {"contents": "<json>"}."""
    contents = outer.get("contents")
    if isinstance(contents, str):
        return _loads(contents)
    if isinstance(outer, dict) and "status_code" in outer:
        return outer  # some relays hand back a parsed object
    raise TMDBUnavailable("Relay response had no `contents` field.")


def _loads(text: str) -> Dict[str, Any]:
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise TMDBUnavailable("Relay returned a non-JSON body.") from exc
    if not isinstance(payload, dict):
        raise TMDBUnavailable("Relay returned an unexpected payload shape.")
    return payload


# Ordered by measured reliability (jina answered 10/10 at ~0.55s; allorigins
# was returning Cloudflare 52x most of the time). Free public services
# rate-limit hard, so each is tried in turn before giving up.
#
# `quoted` records whether the target has to be percent-encoded before being
# pasted into the URL -- relays that take a `?url=` parameter do, ones that take
# the path directly do not.
RELAYS: Tuple[Tuple[str, str, bool, Any], ...] = (
    ("jina", "https://r.jina.ai/{target}", False, _unwrap_jina),
    ("allorigins", "https://api.allorigins.win/get?url={target}", True,
     _unwrap_allorigins),
)

# Tri-state, resolved lazily then memoised:
#   None  -> not determined yet; True -> only a relay reaches TMDB
_via_relay: Optional[bool] = None
#   None  -> unknown; True -> the direct image host is blocked
_via_image_proxy: Optional[bool] = None

# TLS interceptors we can name, so the UI can say *who* is blocking rather than
# just "connection failed".
_KNOWN_INTERCEPTORS = (
    ("sophos", "Sophos SSL VPN"),
    ("zscaler", "Zscaler"),
    ("bluecoat", "Blue Coat / Symantec"),
    ("paloalto", "Palo Alto"),
    ("fortinet", "Fortinet"),
    ("cisco", "Cisco"),
    ("kaspersky", "Kaspersky"),
    ("netskope", "Netskope"),
    ("mcafee", "McAfee"),
    ("symantec", "Symantec"),
    ("avast", "Avast"),
    ("kaspersky", "Kaspersky"),
    ("comodo", "Comodo"),
    ("digicert", "DigiCert"),
)

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


def _peer_issuer(host: str = "api.themoviedb.org") -> Optional[str]:
    """PEM of the certificate `host` presents, or None if we can't read one.

    Read with verification switched off -- this is a diagnostic, not a request,
    and no API key is sent.
    """
    import socket
    import ssl as _ssl
    import time as _time

    # Intercepting proxies often reset the *second* connection in quick
    # succession, so a single failed read is not proof of anything -- retry once.
    for attempt in range(2):
        try:
            ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            with socket.create_connection((host, 443), timeout=6) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as tls:
                    der = tls.getpeercert(binary_form=True)
            if der:
                return _ssl.DER_cert_to_PEM_cert(der)
        except Exception:  # noqa: BLE001 - a diagnostic must never raise
            pass
        if attempt == 0:
            _time.sleep(1.0)
    return None


def _name_interceptor(issuer_pem: Optional[str]) -> Optional[str]:
    """Map a presented certificate to a product name, when we recognise it."""
    if not issuer_pem:
        return None
    # The PEM body carries the issuer's own O=/CN= values, which is where the
    # vendor name lives.
    import base64
    import re

    body = "".join(
        line for line in issuer_pem.splitlines()
        if not line.startswith("-----")
    )
    try:
        der = base64.b64decode(body)
    except Exception:  # noqa: BLE001
        return None
    text = "".join(chr(b) if 32 <= b < 127 else " " for b in der).lower()
    for needle, label in _KNOWN_INTERCEPTORS:
        if needle in text:
            return label
    return None


def _tls_hint() -> str:
    """A short, actionable explanation for a failed TLS handshake."""
    if CA_BUNDLE:
        return (
            f"Still failing with `TMDB_CA_BUNDLE={CA_BUNDLE}` -- check the file "
            "holds the right CA certificate."
        )
    issuer = _peer_issuer()
    named = _name_interceptor(issuer)
    if named:
        return (
            f"Outbound HTTPS is being intercepted by {named}, whose CA this "
            "machine does not trust. Exclude `api.themoviedb.org` and "
            "`image.tmdb.org` from the proxy, or set `TMDB_CA_BUNDLE` in `.env` "
            "to that CA's certificate."
        )
    return (
        "TLS handshake failed and no intercepting certificate was recognised. "
        "A VPN, corporate proxy or antivirus is likely rewriting HTTPS; exclude "
        "`api.themoviedb.org` from it, or set `TMDB_CA_BUNDLE` in `.env`."
    )


def _verify_setting() -> Any:
    if CA_BUNDLE:
        return CA_BUNDLE
    return not INSECURE_SSL


def _client(timeout: float = TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        verify=_verify_setting(),
        headers={"Accept": "application/json"},
    )


def _query_string(params: Dict[str, Any]) -> str:
    from urllib.parse import urlencode

    return urlencode({"api_key": TMDB_API_KEY, "language": TMDB_LANG, **params})


def _relay_request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch an API response through a public relay, trying each in turn.

    Raises the last failure so the caller can report something specific.
    """
    from urllib.parse import quote

    target = f"{TMDB_BASE}{path}?{_query_string(params)}"
    last = "no relay configured"

    for name, template, quoted, unwrap in RELAYS:
        url = template.format(target=quote(target, safe="") if quoted else target)
        try:
            with _client(RELAY_TIMEOUT) as client:
                response = client.get(url)
            if response.status_code != 200:
                last = f"{name} returned HTTP {response.status_code}"
                continue
            try:
                outer = response.json()
            except ValueError:
                last = f"{name} did not return JSON"
                continue
            if not isinstance(outer, dict):
                last = f"{name} returned an unexpected shape"
                continue
            return unwrap(outer)
        except TMDBUnavailable as exc:
            last = f"{name}: {exc}"
        except httpx.RequestError as exc:
            last = f"{name} unreachable ({type(exc).__name__})"

    raise TMDBUnavailable(f"all relays failed -- {last}")


def _relay_hint() -> str:
    if RELAY_MODE == "off":
        return (
            "Set `TMDB_RELAY=auto` in `.env` to let requests go through a public "
            "relay, or exclude `api.themoviedb.org` from the network's block list."
        )
    return (
        "Set `TMDB_CA_BUNDLE` in `.env`, or ask IT to exclude `api.themoviedb.org` "
        "and `image.tmdb.org` from the proxy."
    )


def _request(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    global _via_relay

    if not is_configured():
        raise TMDBUnavailable("TMDB_API_KEY is not set (check your .env file).")

    # Once we know the direct route fails, stop paying for the timeout first.
    direct_first = _via_relay is not True and RELAY_MODE != "only"

    if direct_first:
        try:
            with _client() as client:
                response = client.get(f"{TMDB_BASE}{path}",
                                      params={"api_key": TMDB_API_KEY,
                                              "language": TMDB_LANG, **params})
        except httpx.RequestError as exc:
            _via_relay = True
            if RELAY_MODE == "off":
                raise TMDBUnavailable(
                    f"Could not reach TMDB ({type(exc).__name__}). "
                    f"{_tls_hint()}"
                ) from exc
        else:
            _via_relay = False
            return _finish(response)

    if RELAY_MODE == "off":
        raise TMDBUnavailable(f"TMDB is blocked on this network. {_relay_hint()}")

    try:
        return _relay_request(path, params)
    except TMDBUnavailable as exc:
        raise TMDBUnavailable(f"TMDB relay failed: {exc}") from exc
    except httpx.RequestError as exc:
        raise TMDBUnavailable(
            f"TMDB relay unreachable ({type(exc).__name__}). {_relay_hint()}"
        ) from exc


def _finish(response: "httpx.Response") -> Dict[str, Any]:
    if response.status_code == 401:
        raise TMDBUnavailable("TMDB rejected the API key (401).")
    if response.status_code == 429:
        raise TMDBUnavailable("TMDB rate limit hit (429); try again shortly.")
    if response.status_code != 200:
        raise TMDBUnavailable(f"TMDB returned HTTP {response.status_code}.")
    return response.json()


def route() -> str:
    """Human-readable description of how we are reaching TMDB right now."""
    if not is_configured():
        return "no key"
    if _via_relay is True:
        return "relay"
    if _via_relay is False:
        return "direct"
    return "unknown"


def image_route() -> str:
    """How poster images are being served: direct, proxy, or not yet known."""
    if _via_image_proxy is True:
        return "proxy"
    if _via_image_proxy is False:
        return "direct"
    return "unknown"


def probe() -> Tuple[bool, str]:
    """(reachable, message), memoized briefly so we never hammer a dead host.

    The route that worked is cached alongside the verdict, so a rerun restores
    it instead of paying for the discovery request again. The message is cached
    too: a cached failure still has to explain itself, otherwise the UI shows a
    warning with no reason.
    """
    global _via_relay

    cache = get_cache()
    found, value, fresh = cache.lookup("__probe__")
    if found and fresh:
        reachable, message, via = _unpack_probe(value)
        _via_relay = via
        return reachable, message

    if not is_configured():
        reason = "TMDB_API_KEY is not set. Posters are disabled."
        _remember(False, reason)
        return False, reason

    try:
        _request("/configuration", {})
    except TMDBUnavailable as exc:
        reason = str(exc)
        _remember(False, reason)
        return False, reason

    # Settle the image route now too, so the UI can report it and the first tile
    # does not have to pay for the discovery request.
    direct_images_blocked()
    _remember(True, "")
    return True, ""


def _unpack_probe(value: Any) -> Tuple[bool, str, Optional[bool]]:
    """Read a cached probe record, tolerating the older two-field shape.

    Returns (reachable, message, via_relay).
    """
    if not isinstance(value, (tuple, list)) or not value:
        return False, "", None
    reachable = bool(value[0])
    message = str(value[1]) if len(value) > 1 and value[1] else ""
    via = value[2] if len(value) > 2 else None
    return reachable, message, via if isinstance(via, bool) else None


def _remember(reachable: bool, message: str) -> None:
    get_cache().put("__probe__", (reachable, message, _via_relay), force=True)


def _cached(key: str, loader) -> Tuple[Any, bool]:
    """Return (value, from_cache) using the disk cache as a memo layer."""
    cache = get_cache()
    found, value, fresh = cache.lookup(key)
    if found and fresh:
        return value, True
    value = loader()
    cache.put(key, value, force=True)
    return value, False


def direct_images_blocked() -> bool:
    """Is image.tmdb.org unreachable? Memoised; costs one request the first time.

    Any HTTP answer counts as reachable, including a 404 -- only a transport
    failure means the host itself is blocked.
    """
    global _via_image_proxy
    if _via_image_proxy is not None:
        return _via_image_proxy
    try:
        with _client(8.0) as client:
            # A path that will not exist, so a working host answers 404 quickly
            # while a blocked host fails at the transport layer.
            client.head("https://image.tmdb.org/t/p/w1/__probe__.jpg")
        _via_image_proxy = False
    except httpx.HTTPError:
        _via_image_proxy = True
    return _via_image_proxy


def poster_url(path: Optional[str], size: str = "w500") -> Optional[str]:
    """A poster/backdrop URL that will actually load.

    Networks that block the API usually block the image CDN by the same rule, so
    the two are detected together and routed through the same public proxy.
    """
    if not path:
        return None
    target = f"image.tmdb.org/t/p/{size}{path}"
    if direct_images_blocked():
        return IMAGE_PROXY_TEMPLATE.format(target=target)
    return f"https://{target}"


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
