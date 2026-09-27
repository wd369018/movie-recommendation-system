"""Shared test setup.

The point of this file is that the suite never touches the network. `tmdb_client`
memoises *how* it is reaching TMDB in module-level tri-state flags, and
`poster_url` consults one of them to decide between the direct image host and
the public proxy. A flag left at `None` means "go and find out", which in a test
means a real HTTPS request -- slow, flaky, and dependent on whichever proxy the
machine happens to be behind.

So every test starts and ends with the route pinned, and the handful that care
about proxy behaviour set the flag explicitly instead of discovering it.
"""

from __future__ import annotations

from typing import Iterator

import pytest

import tmdb_client as tmdb


@pytest.fixture(autouse=True)
def pin_network_route() -> Iterator[None]:
    """Freeze the direct/proxy decision and restore it afterwards.

    Pinning to `False` (direct) is the default because that is the route the
    original tests assert against, and it makes `poster_url` a pure function.
    """
    saved = (tmdb._via_relay, tmdb._via_image_proxy)
    tmdb._via_relay = False
    tmdb._via_image_proxy = False
    try:
        yield
    finally:
        tmdb._via_relay, tmdb._via_image_proxy = saved
