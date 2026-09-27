"""Dataset layer for the movie recommender.

Loads the pickled assets and answers recommendation / lookup questions.
Deliberately free of Streamlit and HTTP imports so it stays testable on its own.

Note on `indices.pkl`: its values are exactly `range(len(df))`, so the mapping
carries no information that the DataFrame does not already hold. We therefore
rebuild the lookup from `df` instead, which also lets us handle the ~3,200
duplicate titles that made the old Series-based lookup return a Series.
"""

from __future__ import annotations

import difflib
import os
import pickle
import re
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DF_PATH = os.path.join(BASE_DIR, "df.pkl")
TFIDF_MATRIX_PATH = os.path.join(BASE_DIR, "tfidf_matrix.pkl")

# Words that stay lowercase inside a title unless they lead or close it.
_MINOR_WORDS = frozenset(
    """a an the and but or nor for yet so at by in of on to up as it off out
    over per via from into with about against between through during before
    after above below under again further than once""".split()
)
# Roman-numeral sequels are conventionally uppercase.
_ROMAN_WORDS = frozenset("ii iii iv v vi vii viii ix x xi xii".split())
# Multi-word genres from the dataset (it uses the pre-2010 TMDB genre names).
_MULTIWORD_GENRES = (("science", "fiction"), ("tv", "movie"))

_MAX_CANDIDATES = 10


def _load_pickle(path: str):
    with open(path, "rb") as fh:
        return pickle.load(fh)


def normalize_title(text: str) -> str:
    """Lowercase, strip punctuation, squeeze whitespace.

    Makes `df` titles comparable with TMDB titles, e.g. both "Spider-Man" and
    "spider man" normalize to "spider man".
    """
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _cap_word(word: str, *, lead: bool, trail: bool) -> str:
    if not word:
        return word
    core = re.sub(r"[^A-Za-z0-9]", "", word).lower()
    if not lead and not trail and core in _MINOR_WORDS:
        return word.lower()
    if core in _ROMAN_WORDS:
        return word.upper()
    # Preserve deliberate initialisms such as M.A.S.H. or T.I.M.E.
    if re.fullmatch(r"(?:[A-Za-z]\.){2,}[A-Za-z]?", word):
        return word.upper()
    return word[:1].upper() + word[1:]


def _cap_segment(segment: str, *, lead: bool, trail: bool) -> str:
    """Title-case one whitespace-delimited word, including hyphen compounds."""
    parts = re.split(r"([-/])", segment)
    real = [i for i, p in enumerate(parts) if p and p not in "-/"]
    if not real:
        return segment
    first, last = real[0], real[-1]
    for i in real:
        parts[i] = _cap_word(
            parts[i], lead=(lead and i == first), trail=(trail and i == last)
        )
    return "".join(parts)


def pretty_title(title: str) -> str:
    """Render a display-cased title.

    The dataset stores every title lowercased, so this is only a fallback for
    when TMDB (which returns properly cased titles) is unavailable. Deliberately
    avoids `str.title()`, which would render "the lord of the rings" as
    "The Lord Of The Rings".
    """
    parts = re.split(r"(\s+)", str(title).strip())
    words = [i for i, p in enumerate(parts) if p.strip()]
    if not words:
        return str(title)
    first, last = words[0], words[-1]
    for i in words:
        parts[i] = _cap_segment(
            parts[i], lead=(i == first), trail=(i == last)
        )
    return "".join(parts)


def split_genres(raw: object) -> List[str]:
    """Turn the dataset's space-joined genre string into a list.

    'Science Fiction' and 'TV Movie' must be re-joined, since the column was
    built by joining genre names with a space.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    tokens = str(raw).split()
    for first, second in _MULTIWORD_GENRES:
        joined, i = [], 0
        while i < len(tokens):
            if (i + 1 < len(tokens)
                    and tokens[i].lower() == first
                    and tokens[i + 1].lower() == second):
                joined.append(f"{tokens[i]} {tokens[i + 1]}")  # keep original case
                i += 2
            else:
                joined.append(tokens[i])
                i += 1
        tokens = joined
    return tokens


class Recommendation(NamedTuple):
    """One ranked result.

    `text_score` is the raw cosine similarity and never changes.
    `rank_score` is the value actually sorted on -- equal to `text_score` when
    no popularity blend is applied, so the UI shows a monotonic bar either way.
    """

    row: int
    text_score: float
    rank_score: float


class MovieIndex:
    """In-memory view over `df.pkl` + `tfidf_matrix.pkl`.

    Build it once and reuse it; loading the pickles costs ~2.5s and ~250MB.
    """

    def __init__(
        self,
        df_path: str = DF_PATH,
        matrix_path: str = TFIDF_MATRIX_PATH,
    ) -> None:
        self.df: pd.DataFrame = _load_pickle(df_path)
        self.matrix = _load_pickle(matrix_path)

        if "title" not in self.df.columns:
            raise RuntimeError("df.pkl must contain a 'title' column")

        # Titles are stored lowercased; keep the raw form for TF-IDF alignment.
        self.titles: List[str] = self.titles_of(self.df)
        self.ranks = pd.to_numeric(
            self.df["popularity"], errors="coerce"
        ).fillna(0.0).to_numpy() if "popularity" in self.df.columns else np.zeros(
            len(self.df)
        )
        self.votes = (
            pd.to_numeric(self.df["vote_average"], errors="coerce")
            .fillna(0.0).to_numpy()
            if "vote_average" in self.df.columns
            else np.zeros(len(self.df))
        )

        # normalized title -> every row carrying that title
        self.rows_by_title: Dict[str, List[int]] = {}
        for pos, title in enumerate(self.titles):
            self.rows_by_title.setdefault(normalize_title(title), []).append(pos)

        # normalized title -> the single best row to use as a seed. Remakes and
        # re-releases share a title, so prefer the more popular variant.
        self.seed_by_title: Dict[str, int] = {
            key: max(positions, key=lambda p: (self.ranks[p], -p))
            for key, positions in self.rows_by_title.items()
        }
        self._search_space: List[str] = sorted(self.rows_by_title)

        # Popularity rescaled to [0, 1] by rank. Used only as an optional
        # re-ranking prior; raw cosine scores are never overwritten.
        self._prior: np.ndarray = self._rank01(self.ranks)

    @staticmethod
    def _rank01(values: np.ndarray) -> np.ndarray:
        """Map raw values onto [0, 1] by rank (robust to any input scale)."""
        if values.size == 0:
            return values
        order = values.argsort(kind="stable")
        scaled = np.empty(values.size, dtype=np.float64)
        scaled[order] = np.linspace(0.0, 1.0, values.size)
        return scaled

    # ------------------------------------------------------------------ size
    def __len__(self) -> int:
        return len(self.df)

    @staticmethod
    def titles_of(df: pd.DataFrame) -> List[str]:
        column = "title" if "title" in df.columns else df.columns[0]
        return df[column].astype(str).tolist()

    # ---------------------------------------------------------------- lookup
    def find(self, title: str) -> Optional[int]:
        """Best row index for an exact (normalized) title match, else None."""
        return self.seed_by_title.get(normalize_title(title))

    def variants(self, title: str) -> List[int]:
        """All rows sharing this title, most popular first.

        Ties fall back to the earliest row, matching `seed_by_title`.
        """
        positions = self.rows_by_title.get(normalize_title(title), [])
        return sorted(positions, key=lambda p: (-self.ranks[p], p))

    def search(self, query: str, limit: int = _MAX_CANDIDATES) -> List[int]:
        """Map free text to candidate rows: exact, prefix, substring, then fuzzy."""
        query = (query or "").strip()
        if not query:
            return []

        key = normalize_title(query)
        if key in self.seed_by_title:
            return [self.seed_by_title[key]]

        if len(key) < 2:
            return []

        def rank(positions: Sequence[int]) -> List[int]:
            return sorted(positions, key=lambda p: (-self.ranks[p], p))[:limit]

        prefix = [
            pos
            for norm, pos in self.seed_by_title.items()
            if norm.startswith(key)
        ]
        if prefix:
            return rank(prefix)

        contains = [
            pos
            for norm, pos in self.seed_by_title.items()
            if key in norm
        ]
        if contains:
            return rank(contains)

        close = difflib.get_close_matches(key, self._search_space, n=limit, cutoff=0.72)
        return rank([self.seed_by_title[norm] for norm in close])

    # -------------------------------------------------------- recommend
    def score_all(self, seed: int) -> np.ndarray:
        """Cosine similarity of every movie against `seed`.

        The TF-IDF rows are L2-normalized, so the dot product *is* the cosine
        similarity -- no need to rescale (and far cheaper than
        `cosine_similarity` on the full 45k x 75k matrix).
        """
        query = self.matrix[seed].T
        return (self.matrix @ query).toarray().ravel()

    def recommend(
        self,
        seed: int,
        top_n: int = 12,
        min_score: float = 1e-6,
        popularity_weight: float = 0.0,
    ) -> List[Recommendation]:
        """Top `top_n` similar movies, best first.

        `popularity_weight` (0..1) only re-orders the ranking: pure text
        similarity happily surfaces obscure films whose short blurbs happen to
        share common words, so nudging well-known titles up makes results far
        more useful. `text_score` is left untouched either way.
        """
        if not 0 <= seed < len(self.df):
            raise IndexError(f"seed row {seed} is outside the dataset")
        scores = self.score_all(seed)
        scores[seed] = 0.0

        keep = np.flatnonzero(scores > min_score)
        if keep.size == 0:
            return []
        if popularity_weight > 0:
            ranked = scores[keep] * (1.0 + popularity_weight * self._prior[keep])
        else:
            ranked = scores[keep]

        out: List[Recommendation] = []
        picked = np.argpartition(-ranked, min(top_n, keep.size - 1))[:top_n]
        rows, values = keep[picked], ranked[picked]
        for i in np.argsort(-values, kind="stable"):
            pos = int(rows[i])
            out.append(
                Recommendation(
                    row=pos,
                    text_score=float(scores[pos]),
                    rank_score=float(values[i]),
                )
            )
        return out

    # --------------------------------------------------------- row access
    def row(self, pos: int) -> pd.Series:
        return self.df.iloc[pos]

    def display_title(self, pos: int) -> str:
        return pretty_title(self.titles[pos])

    def get(self, pos: int, column: str, default=None):
        try:
            value = self.row(pos)[column]
        except (KeyError, IndexError):
            return default
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return value
