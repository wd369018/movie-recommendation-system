"""Netflix-style theme for the Streamlit UI.

Streamlit's own theming API cannot express a dark cinematic layout, so the look
is built with injected CSS. Everything here is presentation only -- no data
logic -- and every class is namespaced with `nf-` to avoid clashing with
Streamlit's own styles.
"""

from __future__ import annotations

# Netflix red, near-black surfaces, and the greys used for secondary text.
RED = "#E50914"
BLACK = "#000000"
SURFACE = "#141414"
CARD = "#1f1f1f"

CSS = f"""
<style>
/* ---------- global palette ---------- */
.stApp {{
    background: {BLACK};
    color: #f5f5f5;
}}
html, body, [class*="st-"], [data-testid="stAppViewContainer"] {{
    background: {BLACK};
}}
/* Kill the light-mode defaults that would otherwise peek through */
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stToolbar"] {{ right: 0; }}

h1, h2, h3, h4, h5, h6, p, span, label, li, div {{
    color: #f5f5f5;
}}
a {{ color: {RED}; }}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {{
    background: {SURFACE};
    border-right: 1px solid #2a2a2a;
}}
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ color: {RED}; letter-spacing: .04em; }}

/* ---------- inputs ---------- */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div {{
    background: {CARD} !important;
    border: 1px solid #333;
    border-radius: 6px;
}}
[data-baseweb="input"]:focus-within > div,
[data-baseweb="select"]:focus-within > div {{
    border-color: {RED} !important;
    box-shadow: 0 0 0 1px {RED};
}}
.stTextInput input::placeholder {{ color: #8a8a8a !important; }}

/* ---------- buttons ---------- */
.stButton > button {{
    background: {CARD};
    color: #f5f5f5;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    font-weight: 600;
    transition: background .15s ease, transform .15s ease, border-color .15s ease;
}}
.stButton > button:hover {{
    background: #2b2b2b;
    border-color: {RED};
    color: #fff;
    transform: translateY(-1px);
}}
.stButton > button:focus-visible {{
    box-shadow: 0 0 0 2px {RED};
}}

/* ---------- hero banner ---------- */
.nf-hero {{
    position: relative;
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 1.5rem;
    min-height: 340px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    background: linear-gradient(135deg, #1a1a1a 0%, #0d0d0d 100%);
    border: 1px solid #242424;
}}
.nf-hero img {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: .45;
}}
/* Bottom-up scrim so the text stays readable over any artwork */
.nf-hero::after {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(to top,
        rgba(0,0,0,.96) 0%, rgba(0,0,0,.80) 35%,
        rgba(0,0,0,.35) 65%, rgba(0,0,0,.20) 100%);
}}
.nf-hero-body {{
    position: relative;
    z-index: 2;
    padding: 2.2rem 2rem 1.6rem;
    max-width: 760px;
}}
.nf-hero-kicker {{
    color: {RED};
    font-weight: 700;
    font-size: .74rem;
    letter-spacing: .18em;
    text-transform: uppercase;
    margin-bottom: .5rem;
}}
.nf-hero-title {{
    font-size: 2.6rem;
    font-weight: 800;
    line-height: 1.05;
    margin: 0 0 .6rem 0;
    text-shadow: 0 2px 18px rgba(0,0,0,.9);
}}
.nf-hero-tagline {{
    font-style: italic;
    color: #d0d0d0;
    margin-bottom: .7rem;
    font-size: 1.02rem;
}}
.nf-hero-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: .55rem;
    align-items: center;
    margin-bottom: .8rem;
    font-size: .88rem;
    color: #cfcfcf;
}}
.nf-hero-overview {{
    font-size: .98rem;
    line-height: 1.55;
    color: #e2e2e2;
    margin-bottom: .9rem;
}}
.nf-pill {{
    display: inline-block;
    background: rgba(255,255,255,.10);
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 999px;
    padding: .16rem .68rem;
    font-size: .78rem;
    color: #e8e8e8;
}}
.nf-pill-nf {{ background: {RED}22; border-color: {RED}66; color: #ff9aa0; }}
.nf-score {{
    color: #ffd400;
    font-weight: 700;
}}

/* ---------- section headings ---------- */
.nf-row-title {{
    font-size: 1.32rem;
    font-weight: 700;
    margin: 1.4rem 0 .15rem 0;
    display: flex;
    align-items: center;
    gap: .6rem;
}}
.nf-row-title::before {{
    content: "";
    width: 4px;
    height: 1.15rem;
    background: {RED};
    border-radius: 2px;
}}
.nf-row-sub {{
    color: #9a9a9a;
    font-size: .84rem;
    margin: 0 0 .9rem 1.1rem;
}}

/* ---------- horizontal scroller ---------- */
/*
 * Streamlit renders columns as flex children. Letting the *wrapper* scroll
 * sideways is the only way to get a Netflix-style row, since columns cannot be
 * reordered or made inline by CSS alone.
 */
.nf-scroller {{
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: .8rem;
    margin-bottom: .4rem;
}}
.nf-scroller > div {{
    flex-wrap: nowrap !important;
    gap: .85rem;
    min-width: max-content;
}}
.nf-scroller::-webkit-scrollbar {{ height: 7px; }}
.nf-scroller::-webkit-scrollbar-track {{
    background: #1a1a1a; border-radius: 4px;
}}
.nf-scroller::-webkit-scrollbar-thumb {{
    background: #444; border-radius: 4px;
}}
.nf-scroller::-webkit-scrollbar-thumb:hover {{ background: {RED}; }}

/* ---------- poster card ---------- */
.nf-card {{
    width: 178px;
    flex: 0 0 178px;
    transition: transform .18s ease;
}}
.nf-card:hover {{
    transform: translateY(-6px) scale(1.03);
}}
.nf-card img {{
    width: 100%;
    border-radius: 8px;
    display: block;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    background: #161616;
    border: 1px solid #262626;
}}
.nf-card:hover img {{ border-color: {RED}; box-shadow: 0 8px 26px rgba(0,0,0,.75); }}
.nf-card-title {{
    font-size: .8rem;
    font-weight: 600;
    margin: .5rem 0 .15rem 0;
    line-height: 1.25;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}}
.nf-card-sub {{
    font-size: .7rem;
    color: #8f8f8f;
}}
.nf-card-badge {{
    font-size: .7rem;
    font-weight: 700;
    color: #ffd400;
}}
.nf-poster-fallback {{
    width: 100%;
    aspect-ratio: 2 / 3;
    border-radius: 8px;
    background: linear-gradient(160deg, #202020, #141414);
    border: 1px dashed #3a3a3a;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: .7rem;
    color: #8a8a8a;
    font-size: .72rem;
    line-height: 1.3;
}}

/* ---------- dialog / modal ---------- */
[data-testid="stDialog"] {{ background: #0f0f0f; }}
[data-testid="stDialog"] h1,
[data-testid="stDialog"] h2 {{ color: #fff; }}
[data-testid="stExpander"] {{
    background: {SURFACE};
    border: 1px solid #262626;
    border-radius: 8px;
}}

/* ---------- status messages ---------- */
[data-testid="stAlert"] {{ border-radius: 8px; border: 1px solid #2e2e2e; }}
hr {{ border-color: #262626; }}

/* Hide the "Deploy" button + main menu for a cleaner look */
#MainMenu, footer, [data-testid="stStatusWidget"] {{ visibility: hidden; }}
</style>
"""


def inject() -> None:
    """Mount the theme into the current Streamlit app."""
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
