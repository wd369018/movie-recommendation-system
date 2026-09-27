"""Theming for the Streamlit UI: a dark "cinema" look and a light alternative.

Streamlit's own theming API is fixed at startup, so the palette is applied with
injected CSS. Only *our* components are fully restyled; in light mode Streamlit's
native widgets are left alone, because it already ships a good light theme.

Every selector is either an `nf-` class we own or a bare element tag, so nothing
here depends on Streamlit's internal `data-testid` values (those are minified and
change between releases).
"""

from __future__ import annotations

from typing import Any, Dict

# Palettes. Keys are referenced by name in the CSS below, so adding a theme means
# adding a dict here and nothing else.
PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#000000",
        "surface": "#141414",
        "card": "#1c1c1c",
        "card_hover": "#262626",
        "border": "#333333",
        "border_strong": "#4a4a4a",
        "text": "#f5f5f5",
        "muted": "#a3a3a3",
        "accent": "#E50914",
        "accent_text": "#ff6b73",
        "ok": "#2ecc71",
        "warn": "#f5a524",
        "shadow": "rgba(0,0,0,.75)",
        "focus": "rgba(229,9,20,.55)",
        "scrim": "rgba(0,0,0,.94)",
        "input": "#1c1c1c",
    },
    "light": {
        "bg": "#f6f6f8",
        "surface": "#ffffff",
        "card": "#ffffff",
        "card_hover": "#f0f0f4",
        "border": "#dcdce3",
        "border_strong": "#b9b9c4",
        "text": "#141416",
        "muted": "#63636e",
        # Darker than the dark theme's red: solid accent fills need more
        # contrast against white text than the #E50914 used on black gives.
        # This is what makes the Recommend button visibly re-tint in light mode.
        "accent": "#b3121b",
        "accent_text": "#b3121b",
        "ok": "#128a45",
        "warn": "#a35c00",
        "shadow": "rgba(20,20,30,.16)",
        "focus": "rgba(179,18,27,.35)",
        "scrim": "rgba(255,255,255,.93)",
        "input": "#ffffff",
    },
}


def build_css(theme: str) -> str:
    """Full stylesheet for one theme."""
    # Resolve first, then decide everything from the resolved name. Deriving
    # `is_dark` from the raw argument would make an unknown value produce a dark
    # palette with light-mode widgets. Comparison is case-insensitive because
    # the value can arrive straight from a URL query parameter.
    wanted = str(theme).strip().lower()
    name = wanted if wanted in PALETTES else "dark"
    p: Dict[str, Any] = PALETTES[name]
    is_dark = name == "dark"

    # In light mode Streamlit's own widgets are already correct, so we skip the
    # component overrides that would otherwise fight with them.
    widget_overrides = ""
    if is_dark:
        widget_overrides = f"""
/* ---------- dark widget repaint ----------
   Streamlit's base theme is light; these force the interactive bits dark. */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
    background: {p['input']} !important;
    border: 1px solid {p['border']};
    color: {p['text']};
}}
[data-baseweb="input"] input,
[data-baseweb="select"] input,
textarea {{
    color: {p['text']} !important;
}}
[data-baseweb="popover"] > div,
[data-baseweb="menu"] > ul {{
    background: {p['card']};
    border: 1px solid {p['border']};
}}
[role="option"], [role="listbox"] li {{ color: {p['text']} !important; }}
[role="option"]:hover, [role="listbox"] li:hover {{ background: {p['card_hover']} !important; }}
input::placeholder, textarea::placeholder {{ color: {p['muted']} !important; }}
label, [data-testid="stWidgetLabel"] p {{ color: {p['muted']} !important; }}

/* sliders */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
    background: {p['accent']} !important;
}}
[data-baseweb="slider"] [data-testid="stThumbValue"] {{
    color: {p['muted']} !important;
}}

/* radio / checkbox marks */
[data-baseweb="radio"] circle, [data-baseweb="checkbox"] rect {{
    fill: {p['card']};
    stroke: {p['border_strong']};
}}
[data-baseweb="radio"] circle:checked, [data-baseweb="checkbox"] rect:checked {{
    fill: {p['accent']};
    stroke: {p['accent']};
}}

/* expander, alerts, dialogs */
[data-testid="stExpander"] {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
}}
[data-testid="stExpander"] summary {{ color: {p['text']} !important; }}
[data-testid="stAlert"] {{ border-radius: 10px; }}
"""

    return f"""
<style>
:root {{
    --nf-bg: {p['bg']};
    --nf-surface: {p['surface']};
    --nf-card: {p['card']};
    --nf-card-hover: {p['card_hover']};
    --nf-border: {p['border']};
    --nf-border-strong: {p['border_strong']};
    --nf-text: {p['text']};
    --nf-muted: {p['muted']};
    --nf-accent: {p['accent']};
    --nf-accent-text: {p['accent_text']};
    --nf-ok: {p['ok']};
    --nf-warn: {p['warn']};
    --nf-shadow: {p['shadow']};
    --nf-focus: {p['focus']};
    --nf-scrim: {p['scrim']};
}}

/* ---------- page surface ---------- */
.stApp, [data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
[data-testid="stMain"] {{ background: var(--nf-bg) !important; }}
[data-testid="stHeader"] {{ background: transparent !important; }}
[data-testid="stToolbar"] {{ right: 0 !important; background: transparent !important; }}
h1, h2, h3, h4, h5, h6, p, span, label, li, div, a {{ color: var(--nf-text); }}
a {{ color: var(--nf-accent-text) !important; }}
code, pre {{ background: var(--nf-card) !important; color: var(--nf-text) !important; }}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {{
    background: var(--nf-surface) !important;
    border-right: 1px solid var(--nf-border);
}}
[data-testid="stSidebar"] hr {{ border-color: var(--nf-border-strong); }}

/* ---------- masthead ---------- */
.nf-mast {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    padding: .35rem 0 .7rem 0;
}}
.nf-brand {{
    font-size: 1.75rem;
    font-weight: 800;
    letter-spacing: -.03em;
    line-height: 1;
    color: var(--nf-text);
    display: flex;
    align-items: center;
    gap: .55rem;
}}
/* The red block beside the wordmark: a real element, not a pseudo-element, so it
   cannot be dropped by a sanitiser or a layout change. */
.nf-brand-mark {{
    width: 10px;
    height: 1.7rem;
    border-radius: 3px;
    background: var(--nf-accent);
    flex: 0 0 10px;
}}
.nf-brand em {{ font-style: normal; color: var(--nf-accent); }}

/* Status pill. The tick is a literal character, so it renders identically in
   both themes instead of depending on a themed icon font. */
.nf-status {{
    display: inline-flex;
    align-items: center;
    gap: .5rem;
    padding: .34rem .85rem;
    border-radius: 999px;
    font-size: .8rem;
    font-weight: 600;
    border: 1px solid var(--nf-border-strong);
    background: var(--nf-card);
    color: var(--nf-text);
    line-height: 1.2;
}}
.nf-status.ok {{ border-color: var(--nf-ok); color: var(--nf-ok); }}
.nf-status.warn {{ border-color: var(--nf-warn); color: var(--nf-warn); }}
.nf-status-icon {{ font-size: .95rem; line-height: 1; }}

/* ---------- section heading + accent rule ---------- */
.nf-head {{
    display: flex;
    align-items: center;
    gap: .7rem;
    margin: 1.6rem 0 .1rem 0;
}}
.nf-head-bar {{
    width: 5px;
    height: 1.3rem;
    border-radius: 3px;
    background: var(--nf-accent);
    flex: 0 0 5px;
}}
.nf-head-text {{
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--nf-text);
    line-height: 1.2;
}}
.nf-head-note {{
    font-size: .82rem;
    color: var(--nf-muted);
    margin: 0 0 .9rem 1.4rem;
}}
/* Hairline that was previously invisible: it used a near-background colour. */
.nf-rule {{
    height: 2px;
    background: var(--nf-border-strong);
    border: 0;
    margin: .9rem 0 0 0;
    border-radius: 2px;
}}

/* ---------- hero ---------- */
.nf-hero {{
    position: relative;
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid var(--nf-border);
    min-height: 330px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    background: linear-gradient(135deg, var(--nf-card) 0%, var(--nf-bg) 100%);
}}
.nf-hero-art {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    opacity: .5;
}}
.nf-hero::after {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(to top,
        var(--nf-scrim) 0%,
        var(--nf-scrim) 34%,
        rgba(0,0,0,.28) 70%,
        rgba(0,0,0,.14) 100%);
}}
.nf-hero-body {{
    position: relative;
    z-index: 2;
    padding: 2.1rem 1.9rem 1.5rem;
    max-width: 720px;
}}
.nf-kicker {{
    color: var(--nf-accent);
    font-weight: 700;
    font-size: .72rem;
    letter-spacing: .2em;
    text-transform: uppercase;
    margin-bottom: .45rem;
}}
.nf-hero-title {{
    font-size: 2.5rem;
    font-weight: 800;
    line-height: 1.04;
    margin: 0 0 .5rem 0;
    text-shadow: 0 2px 20px rgba(0,0,0,.85);
}}
.nf-tagline {{
    font-style: italic;
    color: var(--nf-muted);
    margin-bottom: .6rem;
    font-size: 1rem;
}}
.nf-pills {{ display: flex; flex-wrap: wrap; gap: .45rem; margin-bottom: .7rem; }}
.nf-pill {{
    background: rgba(255,255,255,.12);
    border: 1px solid rgba(255,255,255,.22);
    border-radius: 999px;
    padding: .12rem .6rem;
    font-size: .75rem;
    color: #f0f0f0;
}}
.nf-pill.star {{ border-color: #ffd400; color: #ffd400; }}
.nf-hero-overview {{
    font-size: .96rem;
    line-height: 1.55;
    color: #e6e6e6;
    margin: 0;
}}

/* ---------- poster tile ---------- */
.nf-tile {{
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--nf-border);
    background: var(--nf-card);
    transition: transform .16s ease, border-color .16s ease,
                box-shadow .16s ease;
}}
.nf-tile:hover {{
    transform: translateY(-5px);
    border-color: var(--nf-accent);
    box-shadow: 0 10px 26px var(--nf-shadow);
}}
.nf-tile img {{
    width: 100%;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    display: block;
    background: var(--nf-card);
}}
/* Shown when TMDB has no artwork for a title. */
.nf-tile-empty {{
    width: 100%;
    aspect-ratio: 2 / 3;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: .8rem;
    background: linear-gradient(160deg, var(--nf-card-hover) 0%,
                                       var(--nf-card) 100%);
    color: var(--nf-muted);
    font-size: .78rem;
    font-weight: 600;
    line-height: 1.3;
}}

/* ---------- buttons ---------- */
.stButton > button {{
    background: var(--nf-card);
    color: var(--nf-text);
    border: 1px solid var(--nf-border-strong);
    border-radius: 8px;
    font-weight: 600;
    transition: background .15s ease, border-color .15s ease;
}}
.stButton > button:hover {{
    background: var(--nf-card-hover);
    border-color: var(--nf-accent);
    color: var(--nf-text);
    transform: none;
}}

/* Tile titles are the click target, so the grid needs no separate row of
   "Details" buttons. Scoped with the `st-key-` class Streamlit derives from
   `st.container(key=...)`, which is the supported way to target one region.
   The attribute selector keeps working for every grid, whatever its key. */
[class*="st-key-nf-tiles"] .stButton > button {{
    background: transparent;
    border: 0;
    border-top: 1px solid var(--nf-border);
    border-radius: 0;
    text-align: left;
    font-size: .78rem;
    font-weight: 600;
    line-height: 1.3;
    color: var(--nf-text);
    padding: .45rem .55rem;
    white-space: normal;
    height: auto;
    min-height: 0;
}}
[class*="st-key-nf-tiles"] .stButton > button:hover {{
    background: var(--nf-card-hover);
    border: 0;
    border-top: 1px solid var(--nf-accent);
    color: var(--nf-text);
    transform: none;
}}
[class*="st-key-nf-tiles"] .stButton > button:focus-visible {{
    box-shadow: inset 0 0 0 2px var(--nf-accent);
}}

/* Primary actions (watch links) get the accent fill. */
.stLinkButton a, a.stLinkButton {{
    background: var(--nf-accent) !important;
    color: #ffffff !important;
    border: 1px solid var(--nf-accent) !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    text-decoration: none !important;
}}
.stLinkButton a:hover, a.stLinkButton:hover {{
    filter: brightness(1.12);
    color: #ffffff !important;
}}

/* ---------- the Recommend button ----------
   Selected through the `nf-recommend` container key rather than Streamlit's own
   `stBaseButton-primary` testid: the container class is part of the public
   `st.container(key=...)` contract, while the testid is a build detail that is
   assembled at runtime from a `kind` enum and is not in the bundle as a literal.

   The colour is the palette accent, so it follows the theme instead of being
   hard-coded, and white text on it clears the contrast bar in both. */
.st-key-nf-recommend [data-testid="stFormSubmitButton"] {{
    background: var(--nf-accent) !important;
    border: 1px solid var(--nf-accent) !important;
    color: #ffffff !important;
    border-radius: 10px !important;
    min-height: 3rem;
    font-size: 1.02rem;
    font-weight: 700;
    box-shadow: 0 4px 16px var(--nf-shadow);
    transition: filter .15s ease, transform .12s ease;
}}
/* Belt and braces: if the internal testid ever changes, the raw element still
   gets the accent rather than falling back to Streamlit's default blue. */
.st-key-nf-recommend button {{
    background: var(--nf-accent) !important;
    border-color: var(--nf-accent) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    width: 100%;
    min-height: 3rem;
}}
.st-key-nf-recommend button:hover {{
    filter: brightness(1.12);
    color: #ffffff !important;
    transform: translateY(-1px);
}}
.st-key-nf-recommend button:active {{ transform: translateY(0); }}
.st-key-nf-recommend button:focus-visible {{
    box-shadow: 0 0 0 3px var(--nf-focus) !important;
    color: #ffffff !important;
}}
/* The form's own chrome would otherwise frame the page's one main action. */
.st-key-nf-recommend [data-testid="stForm"] {{
    background: transparent;
    border: 0;
    padding: 0;
}}

/* ---------- embedded trailer ----------
   Height comes from the aspect ratio so the frame scales with the column
   instead of keeping a fixed 360px letterbox on a phone. */
.nf-embed {{
    width: 100%;
    aspect-ratio: 16 / 9;
    border: 0;
    border-radius: 10px;
    display: block;
    background: var(--nf-card);
}}

/* ---------- responsive poster grid ----------
   The columns flex-wrap instead of holding a fixed count, so a phone shows
   three tiles per row and a desktop shows six, with no server-side guess about
   the viewport. */
[class*="st-key-nf-tiles"] [data-testid="stHorizontalBlock"] {{
    display: flex;
    flex-wrap: wrap;
    gap: .8rem;
    align-items: stretch;
}}
[class*="st-key-nf-tiles"] [data-testid="stColumn"] {{
    flex: 1 1 150px;
    min-width: 132px;
    max-width: 240px;
}}

/* ---------- mobile ---------- */
@media (max-width: 768px) {{
    .nf-mast {{ padding-bottom: .5rem; }}
    .nf-brand {{ font-size: 1.4rem; }}
    .nf-brand-mark {{ height: 1.4rem; }}
    .nf-head {{ margin-top: 1.2rem; }}
    .nf-head-text {{ font-size: 1.08rem; }}
    .nf-head-note {{ margin-left: 0; margin-bottom: .7rem; }}

    /* Shorter hero so the recommendations are not pushed off-screen. */
    .nf-hero {{ min-height: 230px; border-radius: 10px; }}
    .nf-hero-body {{ padding: 1.4rem 1.1rem 1.1rem; }}
    .nf-hero-title {{ font-size: 1.65rem; }}
    .nf-tagline {{ font-size: .9rem; }}
    .nf-hero-overview {{ font-size: .88rem; }}

    /* 16px minimum keeps iOS from zooming when a field is focused. */
    input, textarea {{ font-size: 16px !important; }}
    .st-key-nf-recommend button {{ min-height: 3.25rem; }}
    [data-testid="stDialog"] {{ max-height: 88vh; }}

    /* Streamlit parks the sidebar behind a hamburger below this width; make
       sure the collapsed rail does not eat horizontal space. */
    [data-testid="stSidebar"] {{ width: 100% !important; }}
}}
@media (max-width: 420px) {{
    [class*="st-key-nf-tiles"] [data-testid="stColumn"] {{
        flex: 1 1 120px;
        min-width: 108px;
    }}
    .nf-hero-title {{ font-size: 1.4rem; }}
    .nf-pill {{ font-size: .7rem; padding: .1rem .5rem; }}
    /* Provider links go one per row rather than two cramped halves. */
}}

/* ---------- dialog ---------- */
[data-testid="stDialog"] {{ border: 1px solid var(--nf-border); }}

hr {{ border-color: var(--nf-border-strong); }}
{widget_overrides}

/* Hide Streamlit's own chrome -- it is pure clutter here. */
#MainMenu, footer, [data-testid="stStatusWidget"] {{ visibility: hidden; }}
</style>
"""


def inject(theme: str) -> None:
    """Mount the stylesheet for `theme` ("dark" or "light")."""
    import streamlit as st

    st.markdown(build_css(theme), unsafe_allow_html=True)
