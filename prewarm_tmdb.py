"""Pre-fetch TMDB artwork, trailers and watch links into `tmdb_cache.pkl`.

The app resolves titles lazily, one lookup per movie, which is fine while you
browse but adds up. Running this first fills the cache so the UI is instant and
keeps working when TMDB is unreachable.

    python prewarm_tmdb.py                    # 2,000 most popular titles
    python prewarm_tmdb.py --limit 20000      # a serious chunk of the catalogue
    python prewarm_tmdb.py --details 500      # + trailers/providers for top 500
    python prewarm_tmdb.py --all              # every one of the 45,447

Safe to interrupt and re-run: anything already cached is skipped. TMDB allows
roughly 50 requests/second, but --delay keeps a comfortable margin so you do not
get throttled.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import List

import tmdb_client as tmdb
from movies import MovieIndex, normalize_title

REGION_CHOICES = ("US", "GB", "IN", "CA", "AU", "DE", "FR", "ES", "BR", "JP")


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-populate the TMDB cache for the movie dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--limit", type=int, default=2000,
        help="How many dataset titles to resolve (most popular first).",
    )
    parser.add_argument(
        "--details", type=int, default=100, metavar="N",
        help="Also fetch trailers/watch providers for the top N of those.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Resolve every title in the dataset (ignores --limit).",
    )
    parser.add_argument(
        "--region", default="US", choices=REGION_CHOICES,
        help="Region whose streaming providers to cache.",
    )
    parser.add_argument(
        "--delay", type=float, default=0.25, metavar="SECONDS",
        help="Pause between TMDB requests.",
    )
    return parser.parse_args(argv)


def already_cached(title: str) -> bool:
    found, _, fresh = tmdb.get_cache().lookup(f"search:{normalize_title(title)}")
    return found and fresh


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    if not tmdb.is_configured():
        print("TMDB_API_KEY is not set. Add it to .env first.", file=sys.stderr)
        return 2

    reachable, message = tmdb.probe()
    if not reachable:
        print(f"Cannot reach TMDB: {message}", file=sys.stderr)
        print(
            "This host is blocked on some networks. Try a VPN or a different "
            "connection, then retry.",
            file=sys.stderr,
        )
        return 3

    index = MovieIndex()
    total = len(index)
    order = index.ranks.argsort()[::-1]  # most popular first
    if not args.all:
        order = order[: min(args.limit, total)]

    print(
        f"Resolving {len(order):,} titles from {total:,} "
        f"(region={args.region}, details for top {args.details:,})\n"
    )

    hits = misses = skipped = failed = 0
    started = time.time()

    for n, pos in enumerate(order, start=1):
        title = index.titles[pos]
        want_details = n <= args.details
        card: dict | None = None

        if already_cached(title):
            skipped += 1
            if want_details:
                # Free: the search response is already memoised, so pull the
                # tmdb id out of it rather than paying for a second request.
                found, cached, _ = tmdb.get_cache().lookup(
                    f"search:{normalize_title(title)}"
                )
                card = cached if found else None
        else:
            try:
                card = tmdb.search_movie(title)
                hits += bool(card)
                misses += not card
            except tmdb.TMDBUnavailable as exc:
                failed += 1
                print(f"\n  stopped at {title!r}: {exc}", file=sys.stderr)
                break
            time.sleep(args.delay)

        if want_details and card:
            try:
                tmdb.movie_details(card["tmdb_id"], region=args.region)
            except tmdb.TMDBUnavailable:
                pass
            else:
                time.sleep(args.delay)

        if n % 100 == 0 or n == len(order):
            rate = n / max(time.time() - started, 1e-6)
            done = hits + misses + skipped
            print(
                f"  {done:>6,}/{len(order):,}  matched {hits:,}  "
                f"not-found {misses:,}  already-cached {skipped:,}  "
                f"failed {failed:,}  ({rate:.1f}/s)"
            )

    tmdb.get_cache().flush()
    elapsed = time.time() - started
    stats = tmdb.get_cache().stats()
    print(
        f"\nDone in {elapsed / 60:.1f} min. "
        f"Cache now holds {stats['total']:,} entries.\n"
        f"Posters load instantly in the app, and still work offline."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
