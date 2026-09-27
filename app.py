"""Movie Recommender -- single Streamlit app (UI + TMDB integration).

Data flow:
    pick a seed movie
      -> local TF-IDF cosine similarity (offline, instant)
      -> resolve each recommendation to TMDB for artwork / trailer / watch links

If TMDB is unreachable the app still works; tiles fall back to a placeholder and
the sidebar names the reason.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import streamlit as st

import netflix_theme
import tmdb_client as tmdb
from movies import MovieIndex, split_genres

st.set_page_config(
    page_title="FLIXFIND",
    page_icon="\U0001f3ac",
    layout="wide",
    initial_sidebar_state="expanded",
)

TOP_N_DEFAULT = 12
GRID_COLUMNS = 6
PALETTE_KEYS = ("dark", "light")
# The catalogue is a US-market TMDB dump, and the region only ever affected the
# where-to-watch links, so it is fixed rather than exposed as a control.
REGION = "US"


# ----------------------------------------------------------------- data layer
@st.cache_resource(show_spinner="Loading 45,447 movies and their TF-IDF vectors...")
def load_index() -> MovieIndex:
    return MovieIndex()


class Settings(NamedTuple):
    top_n: int
    popularity: float
    only_with_posters: bool


# ------------------------------------------------------------------ utilities
def esc(text: Any) -> str:
    """Escape anything before dropping it into raw HTML."""
    return html.escape(str(text if text is not None else ""))


def status_pill(ok: bool, detail: str) -> str:
    """The connection badge. The glyph is a literal character so it renders in
    both themes rather than depending on a themed icon font."""
    if ok:
        return (
            '<span class="nf-status ok">'
            '<span class="nf-status-icon">&#10003;</span>TMDB connected</span>'
        )
    label = "No API key" if not tmdb.is_configured() else "TMDB blocked"
    title = f' title="{esc(detail)}"' if detail else ""
    return (
        f'<span class="nf-status warn"{title}>'
        f'<span class="nf-status-icon">&#9888;</span>{esc(label)}</span>'
    )


def masthead(ok: bool, detail: str) -> None:
    st.markdown(
        '<div class="nf-mast">'
        '<div class="nf-brand">'
        '<span class="nf-brand-mark"></span>FLIX<em>FIND</em>'
        "</div>"
        f"{status_pill(ok, detail)}"
        "</div>"
        '<hr class="nf-rule">',
        unsafe_allow_html=True,
    )


def section_head(text: str, note: str = "") -> None:
    note_html = f'<div class="nf-head-note">{esc(note)}</div>' if note else ""
    st.markdown(
        '<div class="nf-head">'
        '<span class="nf-head-bar"></span>'
        f'<span class="nf-head-text">{esc(text)}</span>'
        "</div>" + note_html,
        unsafe_allow_html=True,
    )


def meta_line(*parts: Optional[str]) -> Optional[str]:
    kept = [p for p in parts if p]
    return "  \u00b7  ".join(kept) if kept else None


def local_genres(index: MovieIndex, pos: int) -> List[str]:
    return split_genres(index.get(pos, "genres"))


def load_card(index: MovieIndex, pos: int) -> Dict[str, Any]:
    """TMDB metadata for a dataset row, falling back to the dataset's own fields.

    The dataset has no TMDB id (and no release year to tell remakes apart), so
    the match is by title. A miss is normal, not exceptional.
    """
    try:
        card = tmdb.resolve(index.titles[pos], region=REGION)
    except tmdb.TMDBUnavailable:
        card = None
    if card:
        return card

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


# ------------------------------------------------------------------- fragments
def hero_html(card: Dict[str, Any], kicker: str) -> str:
    backdrop = card.get("backdrop_url") or card.get("poster_url")
    art = (
        f'<img class="nf-hero-art" src="{esc(backdrop)}" alt="" aria-hidden="true">'
        if backdrop
        else ""
    )

    pills = []
    for genre in (card.get("genres") or [])[:4]:
        pills.append(f'<span class="nf-pill">{esc(genre)}</span>')
    if card.get("year"):
        pills.append(f'<span class="nf-pill">{esc(card["year"])}</span>')
    if card.get("runtime"):
        pills.append(f'<span class="nf-pill">{esc(card["runtime"])} min</span>')
    rating = card.get("vote_average")
    if isinstance(rating, (int, float)) and rating:
        pills.append(f'<span class="nf-pill star">&#9733; {rating:.1f}</span>')

    return (
        '<div class="nf-hero">'
        f"{art}"
        '<div class="nf-hero-body">'
        f'<div class="nf-kicker">{esc(kicker)}</div>'
        f'<div class="nf-hero-title">{esc(card["title"])}</div>'
        + (f'<div class="nf-tagline">{esc(card["tagline"])}</div>'
           if card.get("tagline") else "")
        + f'<div class="nf-pills">{"".join(pills)}</div>'
        + (f'<p class="nf-hero-overview">{esc(card["overview"])}</p>'
           if card.get("overview") else "")
        + "</div></div>"
    )


def tile_html(card: Dict[str, Any]) -> str:
    """Poster artwork, or a placeholder when TMDB has none."""
    poster = card.get("poster_url")
    if poster:
        return (
            '<div class="nf-tile">'
            f'<img src="{esc(poster)}" alt="{esc(card["title"])}" loading="lazy">'
            "</div>"
        )
    return (
        '<div class="nf-tile">'
        '<div class="nf-tile-empty">&#127916;</div>'
        "</div>"
    )


# ---------------------------------------------------------------------- theme
def seed_theme() -> None:
    """Seed the theme from the URL so a refresh keeps the choice.

    Only ever *seeds*; the widget's own return value is the source of truth once
    it exists, so this does not need to run again.
    """
    if "theme" not in st.session_state:
        choice = str(st.query_params.get("theme") or "dark").strip().lower()
        st.session_state.theme = choice if choice in PALETTE_KEYS else "dark"


# --------------------------------------------------------------------- sidebar
def render_sidebar() -> Tuple[Settings, str]:
    st.sidebar.markdown("### Appearance")
    # The widget's return value is read instead of using an `on_change`
    # callback: a callback fires before the widget has been re-registered, so
    # reading its key raises KeyError after a hot reload. A plain return value
    # carries no such ordering hazard.
    choice = st.sidebar.segmented_control(
        "Theme",
        options=["Dark", "Light"],
        key="theme_pick",
        label_visibility="collapsed",
    )
    theme = (choice or "Dark").strip().lower()
    if theme not in PALETTE_KEYS:
        theme = "dark"
    # Keep the URL in step so a refresh restores the same look.
    st.query_params["theme"] = theme
    st.session_state.theme = theme

    st.sidebar.divider()
    st.sidebar.markdown("### Results")
    top_n = st.sidebar.slider("How many", 5, 24, TOP_N_DEFAULT, 1)
    popularity = st.sidebar.slider(
        "Popularity blend", 0.0, 1.0, 0.35, 0.05,
        help="0 = pure text match. Raise it to favour well-known films.",
    )
    only_with_posters = st.sidebar.checkbox("Only titles with artwork", False)

    return Settings(top_n, popularity, only_with_posters), theme


# ---------------------------------------------------------------- search panel
def render_search(index: MovieIndex) -> Optional[int]:
    """Type a title, press Recommend.

    A form keeps the app from re-ranking on every keystroke, which on 45,447
    titles was both slow and made the results flicker as you typed.
    """
    with st.container(key="nf-recommend"):
        with st.form("search", clear_on_submit=False, border=False):
            query = st.text_input(
                "Movie name",
                placeholder="Type a movie name\u2026",
                label_visibility="collapsed",
            ).strip()
            pressed = st.form_submit_button("Recommend", type="primary")

    # Forms batch their widgets, so a sidebar change re-runs with `pressed`
    # False but the text box still holding the last value. Remembering the
    # submitted query is what keeps results on screen through those re-runs.
    if pressed and query:
        st.session_state["last_query"] = query
    submitted = st.session_state.get("last_query", "")

    if not submitted:
        st.caption("Enter any movie name and press Recommend.")
        return None

    matches = index.search(submitted)
    if not matches:
        st.warning(f"No movie in the catalogue matches **{submitted}**.")
        return None
    if len(matches) == 1:
        return matches[0]

    # Flag titles the dataset stores more than once (remakes, re-releases) so
    # they can be told apart.
    labels: Dict[int, str] = {}
    for pos in matches:
        count = len(index.variants(index.titles[pos]))
        labels[pos] = index.display_title(pos) + (f"  ({count} versions)"
                                                  if count > 1 else "")

    st.caption(f"{len(matches)} matches \u2014 pick one:")
    # `dict.get` rather than `list.index`: format_func must be total, or a rerun
    # carrying a stale widget value raises.
    return st.radio(
        "Matches",
        options=matches,
        format_func=labels.get,
        index=0,
        label_visibility="collapsed",
    )


# ----------------------------------------------------------------- result grid
class _Row(NamedTuple):
    """Minimal shape so the variants row can reuse the grid renderer."""

    row: int
    text_score: Optional[float] = None


def render_grid(
    index: MovieIndex,
    recs: List[Any],
    only_with_posters: bool,
    key: str,
) -> None:
    """Poster grid. Each tile's title is the button, so there is no second row
    of controls to keep aligned with the artwork."""
    tiles: List[tuple] = []
    for rec in recs:
        card = load_card(index, rec.row)
        if only_with_posters and not card.get("poster_url"):
            continue
        bits: List[str] = []
        rating = card.get("vote_average")
        if isinstance(rating, (int, float)) and rating:
            bits.append(f"\u2605 {rating:.1f}")
        # The variants row carries no similarity score, so omit the hint
        # rather than claim a match it never computed.
        if rec.text_score is not None:
            bits.append(f"{rec.text_score:.0%} text match")
        tiles.append((card, rec.row, "  \u00b7  ".join(bits)))

    if not tiles:
        st.info("No titles with artwork. Turn off *Only titles with artwork*.")
        return

    # The `key` gives the container a `st-key-nf-tiles-*` class, which is how the
    # stylesheet recognises the tile buttons.
    with st.container(key=f"nf-tiles-{key}"):
        for start in range(0, len(tiles), GRID_COLUMNS):
            for column, (card, row, hint) in zip(
                st.columns(GRID_COLUMNS, gap="small"),
                tiles[start:start + GRID_COLUMNS],
            ):
                with column:
                    st.markdown(tile_html(card), unsafe_allow_html=True)
                    if st.button(
                        card["title"],
                        key=f"{key}-t{row}",
                        width="stretch",
                        help=hint,
                    ):
                        st.session_state["open_details"] = (row, None)


def render_hero(index: MovieIndex, seed: int) -> None:
    card = load_card(index, seed)
    st.markdown(hero_html(card, "Your pick"), unsafe_allow_html=True)
    if card.get("trailer") and card["trailer"].get("key"):
        with st.expander("Watch trailer"):
            embed_trailer(card["trailer"])


def embed_trailer(trailer: Dict[str, str]) -> None:
    # `st.components.v1.html` is deprecated and slated for removal; `st.html` is
    # the replacement. It has no `height` argument, so the frame sizes itself
    # from an aspect ratio -- which also means it shrinks correctly on a phone
    # instead of forcing a 380px-tall letterbox onto a 375px-wide screen.
    st.html(
        '<iframe class="nf-embed" '
        'src="https://www.youtube.com/embed/' + esc(trailer["key"]) + '" '
        'title="' + esc(trailer.get("name", "Trailer")) + '" '
        'allow="accelerometer; autoplay; encrypted-media; gyroscope; '
        'picture-in-picture" allowfullscreen></iframe>',
        width="stretch",
    )


def render_recommendations(index: MovieIndex, seed: int, s: Settings) -> None:
    with st.spinner("Ranking 45,447 movies by cosine similarity..."):
        scored = index.recommend(
            seed, top_n=s.top_n, popularity_weight=s.popularity
        )
    if not scored:
        st.info(
            "Nothing scored above zero against this title \u2014 its text "
            "features look empty. Try a better-known movie."
        )
        return

    section_head(
        f"Because you picked {index.display_title(seed)}",
        "Closest matches on plot, genre and tagline text.",
    )
    render_grid(index, scored, s.only_with_posters, key="recs")


def render_variants(index: MovieIndex, seed: int, s: Settings) -> None:
    """The dataset's other versions of the same title -- remakes and
    re-releases, which the TF-IDF ranking tends to bury."""
    others = [p for p in index.variants(index.titles[seed]) if p != seed]
    if not others:
        return
    section_head(
        "Other versions of this title",
        f"Also in the catalogue as \u201c{index.display_title(seed)}\u201d.",
    )
    render_grid(
        index, [_Row(p) for p in others], s.only_with_posters, key="variants",
    )


# ------------------------------------------------------------------ detail view
@st.dialog("Movie details", width="large")
def details_dialog(
    index: MovieIndex, pos: int, text_score: Optional[float]
) -> None:
    card = load_card(index, pos)
    st.markdown(f"## {esc(card['title'])}")
    if card.get("tagline"):
        st.caption(f"*{esc(card['tagline'])}*")

    line = meta_line(
        str(card["year"]) if card.get("year") else None,
        f"{card['runtime']} min" if card.get("runtime") else None,
        f"\u2605 {card['vote_average']:.1f}"
        if isinstance(card.get("vote_average"), (int, float)) else None,
        f"{card['vote_count']:,} votes" if card.get("vote_count") else None,
        f"{text_score:.1%} text match" if text_score is not None else None,
    )
    if line:
        st.caption(line)
    if card.get("genres"):
        st.caption(" \u00b7 ".join(card["genres"]))

    if card.get("backdrop_url"):
        st.image(card["backdrop_url"], width="stretch")
    if card.get("overview"):
        st.write(card["overview"])

    if card.get("trailer") and card["trailer"].get("key"):
        st.markdown("#### Trailer")
        embed_trailer(card["trailer"])
        st.caption(
            "Trailers stream from YouTube. Full films are not playable here \u2014 "
            "commercial services block embedding."
        )

    st.markdown("#### Where to watch")
    providers = card.get("providers") or []
    if providers:
        st.caption("From TMDB (JustWatch data). A subscription may be required.")
        for start in range(0, len(providers), 2):
            for column, entry in zip(
                st.columns(2, gap="small"), providers[start:start + 2]
            ):
                href = entry.get("link")
                label = f"{entry['name']} \u00b7 {entry['offer']}"
                with column:
                    if href:
                        st.link_button(label, href, width="stretch")
                    else:
                        st.button(label, width="stretch", disabled=True)
    else:
        st.caption("No streaming providers listed for this title here.")

    links = []
    if card.get("imdb_id"):
        links.append(("IMDb", f"https://www.imdb.com/title/{card['imdb_id']}"))
    if card.get("tmdb_id"):
        links.append(
            ("TMDB", f"https://www.themoviedb.org/movie/{card['tmdb_id']}")
        )
    if card.get("homepage"):
        links.append(("Official site", card["homepage"]))
    # st.columns(0) raises, and there may be nothing to link to
    for column, (label, href) in zip(st.columns(len(links)) if links else [], links):
        with column:
            st.link_button(label, href, width="stretch")

    if st.button("Close", width="stretch"):
        st.rerun()


# ----------------------------------------------------------------------- main
def main() -> None:
    try:
        index = load_index()
    except Exception as exc:  # noqa: BLE001 - surface asset problems in the UI
        st.error(f"Could not load the recommendation assets: {exc}")
        st.info("Expected `df.pkl` and `tfidf_matrix.pkl` next to `app.py`.")
        st.stop()

    seed_theme()

    tmdb_ok, detail = tmdb.probe()
    # The sidebar is read first because the theme toggle lives there, and the
    # stylesheet is injected afterwards. CSS applies document-wide, so injecting
    # it later in the run still styles the widgets rendered above it.
    settings, theme = render_sidebar()
    netflix_theme.inject(theme)

    masthead(tmdb_ok, detail)
    seed = render_search(index)

    if seed is None:
        st.caption(f"{len(index):,} films loaded and ready.")
        return

    render_hero(index, seed)
    render_recommendations(index, seed, settings)
    render_variants(index, seed, settings)

    opened = st.session_state.pop("open_details", None)
    if opened is not None:
        details_dialog(index, opened[0], opened[1])


if __name__ == "__main__":
    main()
