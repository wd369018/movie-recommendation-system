"""Tests for the theme CSS and the TLS-interception diagnostics.

Everything here runs offline: `build_css` is pure string work, and the
certificate helpers are exercised against a fake PEM rather than a live host.
"""

from __future__ import annotations

import base64
import json
import re

import httpx
import pytest

import netflix_theme
import tmdb_client as tmdb


# ------------------------------------------------------------------- theme CSS
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_css_is_balanced(theme: str) -> None:
    css = netflix_theme.build_css(theme)
    assert css.count("{") == css.count("}")
    assert css.count("<style>") == css.count("</style>") == 1


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_css_has_no_unformatted_placeholders(theme: str) -> None:
    """An f-string slip would leave a bare {token} in the output."""
    css = netflix_theme.build_css(theme)
    # A lone brace is legal CSS; a lone {word} or {word,} is a leaked format slot.
    assert not re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\s*[,}]", css)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_css_defines_every_variable_it_uses(theme: str) -> None:
    """A var() with no matching --nf-* declaration silently falls back."""
    css = netflix_theme.build_css(theme)
    used = set(re.findall(r"var\((--nf-[a-z-]+)\)", css))
    defined = set(re.findall(r"(--nf-[a-z-]+)\s*:", css))
    assert used <= defined, f"undefined: {sorted(used - defined)}"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_palette_colour_reaches_the_stylesheet(theme: str) -> None:
    """A palette entry nobody emits is a colour you can only set, never see.

    Checked against the value rather than the var name, because a few colours are
    interpolated straight into the dark widget overrides instead of going through
    a custom property.
    """
    css = netflix_theme.build_css(theme)
    for key, value in netflix_theme.PALETTES[theme].items():
        assert value in css, f"{theme}: {key} ({value}) is never used"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_required_selectors_present(theme: str) -> None:
    css = netflix_theme.build_css(theme)
    for selector in (
        "nf-brand-mark",     # the red block beside the wordmark
        "nf-status",         # connection badge
        "nf-rule",           # the hairline under the masthead
        "nf-head-bar",       # accent bar on section headings
        "nf-tile",
        "st-key-nf-tiles",   # tile buttons, via st.container(key=...)
    ):
        assert selector in css, f"{theme} missing {selector}"


def test_tile_button_selector_is_attribute_based() -> None:
    """Grid container keys are prefixed per grid, so an exact-class selector
    would only ever match one of them."""
    css = netflix_theme.build_css("dark")
    assert '[class*="st-key-nf-tiles"]' in css
    assert ".st-key-nf-tiles " not in css


def test_palettes_cover_the_same_keys() -> None:
    assert set(netflix_theme.PALETTES) == {"dark", "light"}
    assert set(netflix_theme.PALETTES["dark"]) == set(netflix_theme.PALETTES["light"])


def test_the_two_themes_do_not_look_the_same() -> None:
    """The mode switch has to be a real change, not a relabelled identical palette.

    `accent` in particular drives the Recommend button's fill, so sharing one
    value across both themes would make the toggle appear to do nothing.
    """
    dark, light = netflix_theme.PALETTES["dark"], netflix_theme.PALETTES["light"]
    assert dark["accent"] != light["accent"]
    assert dark["bg"] != light["bg"]
    assert dark["text"] != light["text"]


def test_white_text_clears_contrast_on_the_accent_fill() -> None:
    """The Recommend button is white on `accent` in both themes.

    WCAG AA for large text is 3:1 and for body text 4.5:1; a filled button's
    label is large bold text, so 3:1 is the bar that applies.
    """
    def luminance(hex_colour: str) -> float:
        hex_colour = hex_colour.lstrip("#")
        channels = []
        for i in (0, 2, 4):
            value = int(hex_colour[i:i + 2], 16) / 255
            channels.append(
                value / 12.92 if value <= 0.04045
                else ((value + 0.055) / 1.055) ** 2.4
            )
        r, g, b = channels
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for theme, palette in netflix_theme.PALETTES.items():
        light_on_accent = (1.0 + 0.05) / (luminance(palette["accent"]) + 0.05)
        assert light_on_accent >= 3.0, (
            f"{theme}: white on {palette['accent']} is only "
            f"{light_on_accent:.2f}:1"
        )


@pytest.mark.parametrize("probe", ["nope", "", "blue", "  "])
def test_unknown_theme_falls_back_to_dark(probe: str) -> None:
    assert netflix_theme.build_css(probe) == netflix_theme.build_css("dark")


@pytest.mark.parametrize("probe", ["Light", "LIGHT", " light "])
def test_theme_name_is_case_and_space_insensitive(probe: str) -> None:
    """The value can come straight from a URL query parameter."""
    assert netflix_theme.build_css(probe) == netflix_theme.build_css("light")


def test_dark_theme_has_widget_overrides_light_does_not() -> None:
    """Streamlit ships a usable light theme; overriding it there would fight it."""
    dark = netflix_theme.build_css("dark")
    light = netflix_theme.build_css("light")
    assert "dark widget repaint" in dark
    assert "dark widget repaint" not in light
    assert len(dark) > len(light)


# ------------------------------------------------------- TLS interception hints
def _fake_pem(*words: str) -> str:
    """A PEM-shaped string whose payload mentions `words`, as a real cert would."""
    der = "".join(words).encode()
    body = base64.b64encode(der).decode()
    return "-----BEGIN CERTIFICATE-----\n" + body + "\n-----END CERTIFICATE-----\n"


@pytest.mark.parametrize(
    "words, expected",
    [
        (("Sophos", "SSL", "CA"), "Sophos SSL VPN"),
        (("Zscaler",), "Zscaler"),
        (("Fortinet",), "Fortinet"),
        (("Netskope",), "Netskope"),
    ],
)
def test_interceptor_is_identified(words, expected) -> None:
    assert tmdb._name_interceptor(_fake_pem(*words)) == expected


def test_unknown_issuer_is_not_guessed() -> None:
    assert tmdb._name_interceptor(_fake_pem("Some", "Random", "Corp")) is None


def test_absent_certificate_is_not_guessed() -> None:
    assert tmdb._name_interceptor(None) is None
    assert tmdb._name_interceptor("") is None


def test_malformed_pem_does_not_raise() -> None:
    assert tmdb._name_interceptor("-----BEGIN CERTIFICATE-----\nnot base64\n") is None


def test_tls_hint_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "CA_BUNDLE", "")
    monkeypatch.setattr(tmdb, "_peer_issuer", lambda *a, **k: _fake_pem("Sophos"))
    hint = tmdb._tls_hint()
    assert "Sophos" in hint
    assert "TMDB_CA_BUNDLE" in hint


def test_tls_hint_respects_a_configured_bundle(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "CA_BUNDLE", "C:/proxy-ca.pem")
    assert "C:/proxy-ca.pem" in tmdb._tls_hint()


def test_tls_hint_falls_back_when_certificate_is_unreadable(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "CA_BUNDLE", "")
    monkeypatch.setattr(tmdb, "_peer_issuer", lambda *a, **k: None)
    hint = tmdb._tls_hint()
    assert "TMDB_CA_BUNDLE" in hint


# ------------------------------------------------- routing around a hard block
# The network this was built on refuses TLS to api.themoviedb.org and
# image.tmdb.org rather than intercepting it, so no CA bundle can fix it. These
# tests pin the two decisions that work around that: relay the API, proxy the
# images. `tests/conftest.py` freezes both flags so nothing here opens a socket.


def test_poster_url_is_direct_when_the_image_host_answers() -> None:
    tmdb._via_image_proxy = False
    assert tmdb.poster_url("/abc.jpg") == "https://image.tmdb.org/t/p/w500/abc.jpg"


def test_poster_url_is_proxied_when_the_image_host_is_blocked() -> None:
    tmdb._via_image_proxy = True
    url = tmdb.poster_url("/abc.jpg")
    assert url == "https://images.weserv.nl/?url=image.tmdb.org/t/p/w500/abc.jpg"
    # The size has to survive the hop, otherwise every tile is full-res.
    assert tmdb.poster_url("/abc.jpg", "w92").endswith("/t/p/w92/abc.jpg")


@pytest.mark.parametrize("path", [None, ""])
def test_poster_url_stays_none_without_a_path(path) -> None:
    assert tmdb.poster_url(path) is None


@pytest.mark.parametrize(
    "flag, expected",
    [(False, "direct"), (True, "proxy"), (None, "unknown")],
)
def test_image_route_is_honest_about_not_being_known_yet(flag, expected) -> None:
    """`bool(None)` is False, which would claim `direct` before anything is known."""
    tmdb._via_image_proxy = flag
    assert tmdb.image_route() == expected


@pytest.mark.parametrize(
    "flag, expected", [(False, "direct"), (True, "relay"), (None, "unknown")],
)
def test_api_route_is_reported(flag, expected) -> None:
    tmdb._via_relay = flag
    assert tmdb.route() == expected


def test_jina_relay_body_is_unwrapped() -> None:
    body = {"images": {"base_url": "x"}, "results": []}
    outer = {"code": 200, "data": {"content": json.dumps(body), "httpStatus": 200}}
    assert tmdb._unwrap_jina(outer) == body


def test_allorigins_relay_body_is_unwrapped() -> None:
    body = {"images": {}, "results": [{"id": 1}]}
    assert tmdb._unwrap_allorigins({"contents": json.dumps(body)}) == body


def test_allorigins_may_hand_back_an_object_directly() -> None:
    """The documented shape is a string, but the service has shipped both."""
    body = {"status_code": 7, "status_message": "Invalid API key"}
    assert tmdb._unwrap_allorigins(body) == body


@pytest.mark.parametrize(
    "outer",
    [
        {"data": {}},              # jina with no content
        {"contents": "not json"},  # a relay that returned HTML
        {},                        # nothing recognisable
    ],
)
def test_malformed_relay_responses_raise_a_readable_error(outer) -> None:
    with pytest.raises(tmdb.TMDBUnavailable) as err:
        tmdb._unwrap_jina(outer)
    assert str(err.value)


def test_relay_url_quoting_is_decided_per_relay() -> None:
    """Only `?url=` relays take a percent-encoded target; the rest take it raw."""
    quoted = [t for _, t, q, _ in tmdb.RELAYS if q]
    raw = [t for _, t, q, _ in tmdb.RELAYS if not q]
    assert any(t.startswith("https://api.allorigins.win/get?url=") for t in quoted)
    assert all("url=" not in t for t in raw)


def test_relay_is_used_when_the_direct_route_fails(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "k" * 32)
    monkeypatch.setattr(tmdb, "_via_relay", None)

    def blocked(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(tmdb, "_client", lambda *a, **k: _FakeClient(blocked))
    monkeypatch.setattr(tmdb, "_relay_request", lambda p, q: {"images": {}})

    assert tmdb._request("/configuration", {}) == {"images": {}}
    assert tmdb._via_relay is True
    assert tmdb.route() == "relay"


def test_relay_is_skipped_when_the_direct_route_works(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "k" * 32)
    monkeypatch.setattr(tmdb, "_via_relay", None)
    monkeypatch.setattr(
        tmdb, "_client", lambda *a, **k: _FakeClient(lambda *a, **kw: _reply(200, {"images": {}}))
    )

    def must_not_run(*a, **k):
        raise AssertionError("relay used even though direct worked")

    monkeypatch.setattr(tmdb, "_relay_request", must_not_run)
    assert tmdb._request("/configuration", {}) == {"images": {}}
    assert tmdb._via_relay is False


def test_relay_off_refuses_to_route_around_the_block(monkeypatch) -> None:
    """`TMDB_RELAY=off` is how a user opts out of handing their key to a third party."""
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "k" * 32)
    monkeypatch.setattr(tmdb, "RELAY_MODE", "off")
    monkeypatch.setattr(tmdb, "_via_relay", None)
    monkeypatch.setattr(
        tmdb, "_client",
        lambda *a, **k: _FakeClient(lambda *a, **kw: (_ for _ in ()).throw(
            httpx.ConnectError("refused"))),
    )
    monkeypatch.setattr(tmdb, "_peer_issuer", lambda *a, **k: None)

    def must_not_run(*a, **k):
        raise AssertionError("relay used while TMDB_RELAY=off")

    monkeypatch.setattr(tmdb, "_relay_request", must_not_run)
    with pytest.raises(tmdb.TMDBUnavailable) as err:
        tmdb._request("/configuration", {})
    assert "TMDB_RELAY=auto" in str(err.value) or "exclude" in str(err.value)


def test_relay_only_skips_the_direct_attempt(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "k" * 32)
    monkeypatch.setattr(tmdb, "RELAY_MODE", "only")
    monkeypatch.setattr(tmdb, "_via_relay", None)

    def must_not_run(*a, **k):
        raise AssertionError("direct route used while TMDB_RELAY=only")

    monkeypatch.setattr(tmdb, "_client", must_not_run)
    monkeypatch.setattr(tmdb, "_relay_request", lambda p, q: {"images": {}})
    assert tmdb._request("/configuration", {}) == {"images": {}}


def test_relay_failure_names_the_last_relay(monkeypatch) -> None:
    """The message has to say which service gave up, or the user cannot report it."""
    monkeypatch.setattr(
        tmdb, "RELAYS",
        (("first", "https://first.test/{target}", False,
          lambda o: (_ for _ in ()).throw(tmdb.TMDBUnavailable("nope"))),
         ("second", "https://second.test/{target}", False,
          lambda o: (_ for _ in ()).throw(tmdb.TMDBUnavailable("also nope")))),
    )
    with pytest.raises(tmdb.TMDBUnavailable) as err:
        tmdb._relay_request("/configuration", {})
    assert "second" in str(err.value)


def test_unconfigured_key_never_reaches_a_relay(monkeypatch) -> None:
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "")

    def must_not_run(*a, **k):
        raise AssertionError("a request went out with no API key")

    monkeypatch.setattr(tmdb, "_relay_request", must_not_run)
    with pytest.raises(tmdb.TMDBUnavailable):
        tmdb._request("/configuration", {})


# --------------------------------------------------------------- tiny doubles
class _Response:
    def __init__(self, status: int, payload) -> None:
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _reply(status: int, payload) -> _Response:
    return _Response(status, payload)


class _FakeClient:
    """Stands in for httpx.Client, with `get` driven by a caller-supplied callable."""

    def __init__(self, handler) -> None:
        self._handler = handler

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, *a, **k):
        return self._handler(url)

    def head(self, url, *a, **k):
        return self._handler(url)
