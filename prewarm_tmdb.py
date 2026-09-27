#!/usr/bin/env python
"""Pre-warm the TMDB cache with the most popular movies from the dataset.

Run this once (or periodically) to populate `tmdb_cache.pkl` so the app is
instant for common searches. Uses the concurrent batch resolver.

Usage:
    python prewarm_tmdb.py [--top N] [--workers W]

The script reads the dataset's popularity/vote_average fields and pre-fetches
the top N titles. With 4 workers and a warm relay, ~50 movies takes ~2-3 min.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import tmdb_client as tmdb
from movies import MovieIndex


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-warm TMDB cache")
    ap.add_argument("--top", type=int, default=60,
                    help="Number of most popular movies to pre-fetch")
    ap.add_argument("--workers", type=int, default=4,
                    help="Concurrent workers (keep low to avoid rate limits)")
    ap.add_argument("--skip-cached", action="store_true",
                    help="Skip titles already in cache (default: True)")
    args = ap.parse_args()

    if not tmdb.is_configured():
        print("ERROR: TMDB_API_KEY not set in .env", file=sys.stderr)
        return 1

    print(f"Loading dataset ({MovieIndex.__doc__})...")
    index = MovieIndex()
    print(f"  {len(index)} movies loaded")

    # Sort by vote_average * log(vote_count+1) as a popularity proxy
    # (we don't have a dedicated popularity column in the dataset)
    scored = []
    for pos in range(len(index)):
        v_avg = index.get(pos, "vote_average")
        v_cnt = index.get(pos, "vote_count")
        if isinstance(v_avg, (int, float)) and v_avg > 0:
            import math
            score = v_avg * math.log((v_cnt or 0) + 1)
            scored.append((score, pos))
    scored.sort(reverse=True)
    top_positions = [pos for _, pos in scored[:args.top]]
    titles = [index.titles[p] for p in top_positions]

    print(f"Pre-warming {len(titles)} titles with {args.workers} workers...")
    print("(This will take a few minutes on a relay-limited network)")

    t0 = time.time()
    results = tmdb.resolve_batch(titles, region="US", max_workers=args.workers)
    elapsed = time.time() - t0

    ok = sum(1 for v in results.values() if v)
    print(f"\nDone in {elapsed:.1f}s: {ok}/{len(titles)} cached")

    # Show cache stats
    cache = tmdb.get_cache()
    stats = cache.stats()
    print(f"Cache now: {stats['total']} entries ({stats['fresh']} fresh)")

    if ok < len(titles):
        failed = [t for t, v in results.items() if not v]
        print(f"Failed ({len(failed)}): {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())