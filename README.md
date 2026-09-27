# 🎬 Movie Recommendation System

Content-based movie recommender over **45,447 films**. It vectorizes each
movie's plot, genres and tagline with TF-IDF, then ranks every other film by
cosine similarity. Posters, trailers and where-to-watch links come from TMDB.

```bash
pip install -r requirements.txt
cp .env.example .env      # add your TMDB_API_KEY
streamlit run app.py
```

## 📂 Files

| File | Role |
| --- | --- |
| `app.py` | The entire UI. Streamlit only -- no separate server. |
| `movies.py` | Dataset layer: title lookup, search, cosine-similarity ranking. |
| `tmdb_client.py` | TMDB access with a persistent cache; degrades to offline. |
| `prewarm_tmdb.py` | Optional batch job to fill the cache ahead of time. |
| `df.pkl` | The dataset: `title, overview, genres, tagline, vote_average, popularity, tags`. |
| `tfidf_matrix.pkl` | L2-normalized sparse TF-IDF matrix, 45,447 × 75,827. |
| `main.py` | **Legacy** FastAPI service, superseded by `app.py`. Optional. |

## 🧠 How recommendations work

1. **TF-IDF vectorization** turns each movie's text into a sparse vector,
   down-weighting filler words and emphasising the distinctive ones.
2. **Cosine similarity** — the stored rows are already L2-normalized, so the
   dot product *is* the cosine similarity. No rescaling needed, and it avoids
   recomputing a full 45,447 × 45,447 matrix.
3. **Popularity re-ranking** (optional, on by default at 0.35). Pure text
   similarity often surfaces obscure films whose short blurbs happen to share
   common words — searching *Inception* used to return *Ufo... Annientare
   S.H.A.D.O.*. The blend re-orders results toward well-known titles without
   touching the similarity score, which is always shown as-is.

A query costs about **0.01s** over the whole catalogue.

## 🔌 Posters, trailers and watch links

The dataset has **no TMDB id and no release year**, so every lookup matches on
title. Remakes and re-releases share a title in the dataset, so matches are not
always exact — a card can show a different film with the same name.

Responses are cached to `tmdb_cache.pkl` for 30 days, which means posters keep
working with no network at all. Pre-fill it if you want instant results:

```bash
python prewarm_tmdb.py                   # 2,000 most popular titles
python prewarm_tmdb.py --limit 20000     # a large slice of the catalogue
python prewarm_tmdb.py --all             # everything (45,447)
```

**On trailers and streaming.** Trailers embed from YouTube and work fine.
Where-to-watch links come from TMDB's JustWatch data and open the provider's own
page. Full films from commercial services (Netflix, Prime, Disney+) **cannot** be
embedded — they use DRM and block framing. Playable video needs a source you
control: your own files, or public-domain/CC titles.

## ⚠️ If posters don't load

Check the sidebar status first.

- **`TMDB_API_KEY` missing** → copy `.env.example` to `.env` and add your key.
- **"TMDB is unreachable"** → the host is blocked on your network. DNS resolves
  and the port opens, but the TLS handshake fails, which is what a regional
  block or a TLS-inspecting proxy looks like. A VPN or a different connection
  fixes it. The app still works offline; you just get text cards.
- **Images load, metadata doesn't** → the key is likely wrong or expired.

To confirm from a terminal:

```bash
python -c "import tmdb_client as t; print(t.probe())"
```

## 🧪 Tests

```bash
python -m pytest tests/ -v     # 55 tests, no network or API key needed
```

## 🔒 Security

`.env` **is committed in this repository's history** (commits `07d53f8`,
`6874936`, `119ba8a`), so the current key is exposed. Rotate it at
<https://www.themoviedb.org/settings/api>, then purge it from history with
`git filter-repo --path .env --invert-paths`. `.gitignore` has since been
corrected; `.env.example` documents the expected variables.
