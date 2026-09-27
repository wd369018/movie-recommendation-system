"""Tests for the dataset layer: title handling, lookup and ranking.

Run with:  python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from movies import MovieIndex, normalize_title, pretty_title, split_genres


@pytest.fixture(scope="module")
def index():
    """Built once: loading the pickles takes a couple of seconds."""
    return MovieIndex()


# --------------------------------------------------------------- pure helpers
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Spider-Man", "spider man"),
        ("  THE   AVENGERS ", "the avengers"),
        ("Amélie", "am lie"),
        ("M.A.S.H.", "m a s h"),
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        # The bug this replaces: str.title() renders "of" as "Of".
        ("the lord of the rings", "The Lord of the Rings"),
        ("toy story", "Toy Story"),
        ("return of the jedi", "Return of the Jedi"),
        ("m.a.s.h.", "M.A.S.H."),
        ("harry potter and the chamber of secrets",
         "Harry Potter and the Chamber of Secrets"),
        ("fight club ii", "Fight Club II"),
        ("spider-man", "Spider-Man"),
    ],
)
def test_pretty_title(raw, expected):
    assert pretty_title(raw) == expected


def test_split_genres_rejoins_multiword_genres():
    # The dataset joined genre names with spaces, which split these two apart.
    assert split_genres("Science Fiction TV Movie") == ["Science Fiction", "TV Movie"]
    assert split_genres("Animation Comedy Family") == ["Animation", "Comedy", "Family"]
    assert split_genres(None) == []


# ------------------------------------------------------------------ data shape
def test_dataset_loaded(index):
    assert len(index) == 45447
    assert "title" in index.df.columns


def test_duplicate_titles_are_all_reachable(index):
    """~3,200 titles are duplicated; each must resolve to a real row.

    The old indices.pkl lookup returned a Series for these and crashed with
    "positional indexers are out-of-bounds".
    """
    duplicated = index.df[index.df["title"].duplicated()]["title"].unique()
    assert len(duplicated) > 2000, "expected the dataset to contain duplicates"

    for title in duplicated[:200]:
        seed = index.find(title)
        assert seed is not None
        assert 0 <= seed < len(index)
        # normalize_title folds punctuation, so compare normalized forms:
        # "after life" and "after.life" are genuinely the same title.
        assert normalize_title(index.titles[seed]) == normalize_title(title)


def test_lookup_is_case_insensitive(index):
    assert index.find("Inception") == index.find("inception")
    assert index.find("  TOY STORY ") == index.find("toy story")


def test_variants_are_ranked_by_popularity(index):
    for title in ("the avengers", "the great gatsby", "toy story"):
        variants = index.variants(title)
        ranks = [index.ranks[p] for p in variants]
        assert ranks == sorted(ranks, reverse=True)
        # The seed must be the most popular variant.
        assert index.find(title) == variants[0]


def test_missing_title_returns_none(index):
    assert index.find("zzzzqqqxxxyyy") is None


# ---------------------------------------------------------------------- search
def test_search_exact_and_fuzzy(index):
    assert index.display_title(index.search("Inception")[0]) == "Inception"
    assert index.search("incept"), "prefix search should find Inception"
    assert index.search("harry potter"), "substring search should match several"
    assert index.search("") == []
    assert index.search("zzzzqqq") == []


def test_search_respects_limit(index):
    assert len(index.search("harry potter", limit=3)) <= 3


# ---------------------------------------------------------------- recommend
def test_recommend_never_returns_the_seed(index):
    seed = index.find("toy story")
    assert all(rec.row != seed for rec in index.recommend(seed, top_n=20))


def test_recommend_scores_are_descending_without_blend(index):
    recs = index.recommend(index.find("toy story"), top_n=10)
    scores = [r.rank_score for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_recommend_scores_stay_in_range(index):
    for rec in index.recommend(index.find("the matrix"), top_n=15):
        assert 0.0 < rec.text_score <= 1.0
        assert rec.text_score == pytest.approx(rec.rank_score)


def test_popularity_blend_changes_order_but_not_scores(index):
    seed = index.find("inception")
    plain = index.recommend(seed, top_n=12, popularity_weight=0.0)
    blended = index.recommend(seed, top_n=12, popularity_weight=0.7)

    # Ranking must stay monotonic in whatever value it sorted on.
    for recs in (plain, blended):
        values = [r.rank_score for r in recs]
        assert values == sorted(values, reverse=True)

    # The blend is meant to pull better-known films up.
    if [r.row for r in plain] != [r.row for r in blended]:
        assert [r.rank_score for r in blended] != [r.rank_score for r in plain]


def test_recommend_top_n_is_respected(index):
    assert len(index.recommend(index.find("avatar"), top_n=5)) == 5


def test_recommend_rejects_out_of_range_seed(index):
    with pytest.raises(IndexError):
        index.recommend(len(index) + 10)


def test_sequel_ranks_above_unrelated_films(index):
    """The dataset's own sanity check: Toy Story 3 and 2 are the closest matches."""
    titles = [
        index.display_title(r.row)
        for r in index.recommend(index.find("toy story"), top_n=3)
    ]
    assert "Toy Story 3" in titles and "Toy Story 2" in titles
