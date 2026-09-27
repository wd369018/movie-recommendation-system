"""Movie Recommender -- single Streamlit app (UI + TMDB integration).

Netflix-style dark UI on top of a content-based recommender.

Data flow:
    pick a seed movie
      -> local TF-IDF cosine similarity (offline, instant)
      -> resolve each recommendation to TMDB for artwork / trailer / watch links

If TMDB is unreachable the app still works; it just falls back to text cards.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

import netflix_theme
import tmdb_client as tmdb
from movies import MovieIndex, pretty_title, split_genres

st.set_page_config(
    page_title="Netflix · Movie Recommender",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)
netflix_theme.inject()

TOP_N_DEFAULT = 12
CARD_WIDTH = 178
REGIONS = {
    "US": "United States",
    "GB": "United Kingdom",
    "IN": "India",
    "CA": "Canada",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "ES": "Spain",
    "BR": "Brazil",
    "JP": "Japan",
}


# ----------------------------------------------------------------- data layer
@st.cache_resource(show_spinner="Loading 45,447 movies and their TF-IDF vectors...")
def load_index() -> MovieIndex:
    return MovieIndex()


@st.cache_resource
def cache_store() -> tmdb.TMDBCache:
    return tmdb.get_cache()


# ------------------------------------------------------------------ utilities
def esc(text: Any) -> str:
    """Escape anything before dropping it into raw HTML."""
    return html.escape(str(text if text is not None else ""))


def card_html(card: Dict[str, Any], subtitle: str = "") -> str:
    """One poster tile.

    The tile is a real link so it works without JavaScript; the button that
    follows opens the details dialog. Both point at the same movie.
    """
    title = esc(card["title"])
    poster = card.get("poster_url")
    if poster:
        art = (
            f'<img src="{esc(poster)}" alt="{title}" loading="lazy" '
            f'title="{title}">'
        )
    else:
        art = f'<div class="nf-poster-fallback">{title}</div>'

    badge = ""
    rating = card.get("vote_average")
    if isinstance(rating, (int, float)) and rating:
        badge = f'<div class="nf-card-badge">★ {rating:.1f}</div>'

    sub = f'<div class="nf-card-sub">{esc(subtitle)}</div>' if subtitle else ""
    return (
        f'<div class="nf-card">{art}'
        f'<div class="nf-card-title">{title}</div>{badge}{sub}</div>'
    )


def hero_html(card: Dict[str, Any], kicker: str) -> str:
    """The full-width featured panel at the top of the page."""
    title = esc(card["title"])
    backdrop = card.get("backdrop_url") or card.get("poster_url")
    art = (
        f'<img src="{esc(backdrop)}" alt="" aria-hidden="true">'
        if backdrop
        else ""
    )

    pills = []
    for genre in (card.get("genres") or [])[:4]:
        pills.append(f'<span class="nf-pill">{esc(genre)}</span>')
    for year, runtime, rating in (
        (card.get("year"),
         card.get("runtime"),
         card.get("vote_average")),
    ):
        if year:
            pills.append(f'<span class="nf-pill">{esc(year)}</span>')
        if runtime:
            pills.append(f'<span class="nf-pill">{esc(runtime)} min</span>')
        if isinstance(rating, (int, float)) and rating:
            pills.append(f'<span class="nf-pill nf-score">★ {rating:.1f}</span>')

    overview = card.get("overview")
    overview_html = (
        f'<div class="nf-hero-overview">{esc(overview)}</div>'
        if overview
        else ""
    )
    tagline = card.get("tagline")
    tagline_html = (
        f'<div class="nf-hero-tagline">{esc(tagline)}</div>' if tagline else ""
    )

    return f"""
    <div class="nf-hero">{art}
      <div class="nf-hero-body">
        <div class="nf-hero-kicker">{esc(kicker)}</div>
        <div class="nf-hero-title">{title}</div>
        {tagline_html}
        <div class="nf-hero-meta">{''.join(pills)}</div>
        {overview_html}
      </div>
    </div>
    """


def row_html(cards: List[Dict[str, Any]], subtitles: List[str]) -> str:
    """A horizontally scrollable row of poster tiles."""
    tiles = "".join(
        card_html(card, subtitles[i] if i < len(subtitles) else "")
        for i, card in enumerate(cards)
    )
    return f'<div class="nf-scroller"><div style="display:flex">{tiles}</div></div>'


def meta_line(*parts: Optional[str]) -> Optional[str]:
    kept = [p for p in parts if p]
    return "  ·  ".join(kept) if kept else None


def local_genres(index: MovieIndex, pos: int) -> List[str]:
    return split_genres(index.get(pos, "genres"))


def resolve_card(
    index: MovieIndex, pos: int, region: str
) -> Optional[Dict[str, Any]]:
    """TMDB record for a dataset row, or None if TMDB has no match.

    The dataset has no TMDB id (and no release year to disambiguate remakes), so
    the match is by title. A miss is normal, not exceptional.
    """
    try:
        return tmdb.resolve(index.titles[pos], region=region)
    except tmdb.TMDBUnavailable:
        return None


def fallback_details(index: MovieIndex, pos: int) -> Dict[str, Any]:
    """Dataset-only metadata, used when TMDB is unavailable."""
    overview = index.get(pos, "overview")
    if overview and str(overview) == str(index.get(pos, "tags", "")):
        overview = None  # `tags` is just overview+genres; avoid echoing it
    return {
        "tmdb_id": None,
        "title": index.display_title(pos),
        "overview": overview,
        "tagline": index.get(pos, "tagline"),
        "year": None,
        "runtime": None,
        "vote_average": index.get(pos, "vote_average"),
        "vote_count": None,
        "poster_url": None,
        "backdrop_url": None,
        "genres": local_genres(index, pos),
        "trailer": None,
        "providers": [],
        "homepage": None,
        "imdb_id": None,
    }


def load_card(index: MovieIndex, pos: int, region: str) -> Dict[str, Any]:
    """TMDB metadata for a row, falling back to the dataset's own fields."""
    return resolve_card(index, pos, region) or fallback_details(index, pos)


# --------------------------------------------------------------------- header
def render_sidebar(tmdb_ok: bool) -> Tuple[int, float, str, bool]:
    st.sidebar.markdown("### 🎬 FLIXFIND")
    st.sidebar.caption(
        "Content-based recommendations: TF-IDF vectors over plot, genre and "
        "tagline text, ranked by cosine similarity."
    )

    st.sidebar.divider()
    st.sidebar.markdown("#### ⚙️ Settings")
    top_n = st.sidebar.slider(
        "Recommendations", min_value=5, max_value=24, value=TOP_N_DEFAULT, step=1
    )
    popularity = st.sidebar.slider(
        "Popularity blend", min_value=0.0, max_value=1.0, value=0.35, step=0.05,
        help=(
            "0 = pure text similarity. Higher values favour well-known films. "
            "Text similarity alone often surfaces obscure titles whose short "
            "blurb happens to share common words."
        ),
    )
    region_label = st.sidebar.selectbox(
        "Streaming region", list(REGIONS.values()), index=0
    )
    region = next(k for k, v in REGIONS.items() if v == region_label)
    only_with_posters = st.sidebar.checkbox(
        "Hide titles without artwork", value=False,
        help="Useful when many matches are missing from TMDB.",
    )

    st.sidebar.divider()
    st.sidebar.markdown("#### 🌐 TMDB artwork")
    if not tmdb.is_configured():
        st.sidebar.error("`TMDB_API_KEY` is missing from `.env`")
    elif not tmdb_ok:
        st.sidebar.warning("TMDB unreachable — showing text-only results.")
        st.sidebar.caption(
            "`api.themoviedb.org` failed its TLS handshake on this machine. A VPN "
            "or another network usually fixes it; the app keeps working without it."
        )
    else:
        st.sidebar.success("Connected to TMDB")

    stats = cache_store().stats()
    st.sidebar.caption(
        f"Cached lookups: **{stats['total']}** ({stats['fresh']} fresh)"
    )
    with st.sidebar.expander("Cache tools"):
        st.caption(
            "Lookups are cached to `tmdb_cache.pkl` for 30 days, so posters and "
            "watch links survive restarts and network outages."
        )
        if st.button("Save cache to disk", width="stretch"):
            cache_store().flush()
            st.success("Saved.")
        if st.button("Clear cache", width="stretch"):
            cache_store().clear()
            st.rerun()
    return top_n, popularity, region, only_with_posters


# ---------------------------------------------------------------- search panel
def render_search(index: MovieIndex) -> Optional[int]:
    st.markdown(
        f'<div class="nf-row-title" style="font-size:1.6rem;margin-top:.6rem">'
        f"Find something you like</div>"
        f'<div class="nf-row-sub" style="margin-bottom:1rem">'
        f"Search {len(index):,} films, then pick the one whose row you want to see."
        f"</div>",
        unsafe_allow_html=True,
    )

    query = st.text_input(
        "Movie title", placeholder="🔍  e.g. Inception, Toy Story, The Avengers",
        label_visibility="collapsed",
    )

    if not query.strip():
        st.markdown(
            '<div class="nf-row-sub" style="margin:.6rem 0 0 0">'
            "Tip: start typing — results appear as you go.</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Or browse the full catalogue"):
            choice = st.selectbox(
                "All movies", index._search_space,  # noqa: SLF001 - same package
                format_func=pretty_title, index=None,
                placeholder=f"Choose from {len(index):,} movies...",
            )
            if choice:
                return index.seed_by_title[choice]
        return None

    matches = index.search(query)
    if not matches:
        st.warning(f"No movie in the catalogue matches **{query}**.")
        return None
    if len(matches) == 1:
        return matches[0]

    # Flag titles the dataset stores more than once (remakes, re-releases) so
    # they can be told apart.
    labels: Dict[int, str] = {}
    for pos in matches:
        count = len(index.variants(index.titles[pos]))
        suffix = f"  ({count} versions)" if count > 1 else ""
        labels[pos] = f"{index.display_title(pos)}{suffix}"

    st.markdown(f"**{len(matches)} matches** — pick one:")
    # `dict.get` rather than `list.index`: format_func must be total, or a rerun
    # carrying a stale widget value raises.
    return st.radio(
        "Matches", options=matches, format_func=labels.get,
        index=0, label_visibility="collapsed",
    )


# ------------------------------------------------------------- hero + results
def render_hero(index: MovieIndex, seed: int, region: str) -> None:
    card = load_card(index, seed, region)
    st.markdown(hero_html(card, "Your pick"), unsafe_allow_html=True)

    # Trailer / details live below the hero so the page still works when the
    # artwork is missing.
    if card.get("trailer") and card["trailer"].get("key"):
        with st.expander("▶️  Watch trailer"):
            _embed_trailer(card["trailer"])


def _embed_trailer(trailer: Dict[str, str]) -> None:
    components.html(
        f"""
        <iframe width="100%" height="380" style="border:0;border-radius:8px"
                src="https://www.youtube.com/embed/{esc(trailer['key'])}"
                title="{esc(trailer.get('name', 'Trailer'))}"
                allow="accelerometer; autoplay; encrypted-media; gyroscope;
                       picture-in-picture" allowfullscreen></iframe>
        """,
        height=400,
    )


def render_row(
    index: MovieIndex,
    recs: List[Any],
    region: str,
    only_with_posters: bool,
) -> None:
    """A single scrollable row of poster tiles with a details button under each."""
    cards: List[Dict[str, Any]] = []
    subtitles: List[str] = []
    buttons: List[int] = []
    best = max((r.rank_score for r in recs), default=1.0) or 1.0

    for rec in recs:
        card = load_card(index, rec.row, region)
        if only_with_posters and not card.get("poster_url"):
            continue
        cards.append(card)
        # Show the raw cosine similarity; the bar is the blended rank score.
        subtitles.append(f"{rec.text_score:.0%} match")
        buttons.append(rec.row)

    if not cards:
        st.info("No titles with artwork. Turn off *Hide titles without artwork*.")
        return

    st.markdown(row_html(cards, subtitles), unsafe_allow_html=True)

    # Real buttons beneath the row: the tiles are images, so each needs its own
    # control to open the details dialog.
    columns = st.columns(len(buttons), gap="small")
    for column, pos in zip(columns, buttons):
        with column:
            if st.button("Details", key=f"details_{pos}", width="stretch"):
                rec = next(r for r in recs if r.row == pos)
                st.session_state["open_details"] = (pos, rec.text_score)


def render_recommendations(
    index: MovieIndex,
    seed: int,
    top_n: int,
    popularity: float,
    region: str,
    only_with_posters: bool,
) -> None:
    with st.spinner("Ranking 45,447 movies by cosine similarity..."):
        scored = index.recommend(seed, top_n=top_n, popularity_weight=popularity)

    if not scored:
        st.info(
            "Nothing scored above zero against this title — its text features "
            "look empty. Try a better-known movie."
        )
        return

    st.markdown(
        f'<div class="nf-row-title">Because you picked '
        f"{esc(index.display_title(seed))}</div>"
        f'<div class="nf-row-sub">Each film below overlaps most with your pick '
        f"on plot, genre and tagline text. Scroll sideways for more.</div>",
        unsafe_allow_html=True,
    )
    render_row(index, scored, region, only_with_posters)


def render_similar_to_picks(
    index: MovieIndex, seed: int, region: str, only_with_posters: bool
) -> None:
    """A second row: the dataset's other versions of the same title.

    Surfaces remakes and re-releases, which the TF-IDF ranking tends to bury.
    """
    others = [p for p in index.variants(index.titles[seed]) if p != seed]
    if not others:
        return

    st.markdown(
        '<div class="nf-row-title">More like this title</div>'
        f'<div class="nf-row-sub">Other versions of '
        f"{esc(index.display_title(seed))} in the catalogue.</div>",
        unsafe_allow_html=True,
    )

    class _Row:  # reuse render_row's shape without re-running the ranker
        def __init__(self, row: int):
            self.row = row
            self.text_score = 1.0
            self.rank_score = 1.0

    render_row(index, [_Row(p) for p in others], region, only_with_posters)


# ------------------------------------------------------------------ detail view
@st.dialog("Movie details", width="large")
def details_dialog(
    index: MovieIndex, pos: int, region: str, text_score: Optional[float] = None
) -> None:
    card = load_card(index, pos, region)
    if card.get("tmdb_id") is None and not card.get("poster_url"):
        st.caption(
            f"TMDB has no match for *{index.display_title(pos)}* — showing "
            "catalogue metadata."
        )

    st.markdown(f"## {esc(card['title'])}")
    if card.get("tagline"):
        st.markdown(f"*{esc(card['tagline'])}*")

    if text_score is not None:
        st.caption(
            f"Text similarity to your pick: **{text_score:.1%}** "
            "(cosine similarity of TF-IDF vectors)"
        )

    line = meta_line(
        str(card["year"]) if card.get("year") else None,
        f"{card['runtime']} min" if card.get("runtime") else None,
        f"★ {card['vote_average']:.1f}"
        if isinstance(card.get("vote_average"), (int, float)) else None,
        f"({card['vote_count']:,} votes)" if card.get("vote_count") else None,
    )
    if line:
        st.caption(line)
    if card.get("genres"):
        st.caption(" · ".join(card["genres"]))

    if card.get("backdrop_url"):
        st.image(card["backdrop_url"], width="stretch")
    if card.get("overview"):
        st.write(card["overview"])

    if card.get("trailer") and card["trailer"].get("key"):
        st.markdown("#### ▶️ Trailer")
        _embed_trailer(card["trailer"])
        st.caption(
            "Trailers stream from YouTube. Full films are not playable here — "
            "commercial services block embedding."
        )

    providers = card.get("providers") or []
    if providers:
        st.markdown(f"#### 📺 Where to watch ({REGIONS.get(region, region)})")
        st.caption(
            "Provider links from TMDB (JustWatch data). They open the service's "
            "own watch page — a subscription may be required."
        )
        for start in range(0, len(providers), 4):
            chunk = providers[start:start + 4]
            for column, entry in zip(st.columns(4, gap="small"), chunk):
                with column:
                    if entry.get("logo_url"):
                        st.image(entry["logo_url"], width=64)
                    if entry.get("link"):
                        st.link_button(
                            f"{entry['name']} · {entry['offer']}",
                            entry["link"], width="stretch",
                        )
                    else:
                        st.caption(f"{entry['name']} · {entry['offer']}")
    else:
        st.caption(
            "No streaming providers listed for this title in "
            f"{REGIONS.get(region, region)}."
        )

    links = []
    if card.get("imdb_id"):
        links.append(("IMDb", f"https://www.imdb.com/title/{card['imdb_id']}"))
    if card.get("tmdb_id"):
        links.append(
            ("TMDB", f"https://www.themoviedb.org/movie/{card['tmdb_id']}")
        )
    if card.get("homepage"):
        links.append(("Official site", card["homepage"]))
    if links:  # st.columns(0) raises, and there may be nothing to link to
        for column, (label, href) in zip(st.columns(len(links)), links):
            with column:
                st.link_button(label, href, width="stretch")

    if st.button("Close", width="stretch"):
        st.rerun()


# ----------------------------------------------------------------------- main
def main() -> None:
    try:
        index = load_index()
    except Exception as exc:  # noqa: BLE001 - surface any asset problem in the UI
        st.error(f"Could not load the recommendation assets: {exc}")
        st.info("Expected `df.pkl` and `tfidf_matrix.pkl` next to `app.py`.")
        st.stop()

    tmdb_ok, _ = tmdb.probe()
    top_n, popularity, region, only_with_posters = render_sidebar(tmdb_ok)

    st.markdown(
        '<div style="font-size:2.1rem;font-weight:800;letter-spacing:-.02em;'
        'margin:.2rem 0 .1rem 0">FLIXFIND</div>'
        '<div class="nf-row-sub" style="margin:0 0 1.2rem 0">'
        "Pick a film. Get the most similar ones — with posters, trailers and "
        "where-to-watch links.</div>",
        unsafe_allow_html=True,
    )

    seed = render_search(index)
    if seed is None:
        st.markdown("---")
        st.caption(
            f"{len(index):,} films loaded and ready. "
            f"{'TMDB connected.' if tmdb_ok else 'Running in offline mode.'}"
        )
        return

    render_hero(index, seed, region)
    render_recommendations(index, seed, top_n, popularity, region, only_with_posters)
    render_similar_to_picks(index, seed, region, only_with_posters)

    opened = st.session_state.pop("open_details", None)
    if opened is not None:
        details_dialog(index, opened[0], region, opened[1])


if __name__ == "__main__":
    main()
