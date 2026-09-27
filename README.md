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

The status pill in the top-right of the page tells you which case you're in.

- **"No API key"** → copy `.env.example` to `.env` and add your key.
- **"TMDB blocked"** → the app cannot reach TMDB from this machine. There are two
  quite different reasons, and they need different fixes:
  - **A TLS-inspecting proxy.** The network re-signs HTTPS with its own CA, so
    Python rejects the certificate. The app names the vendor when it recognises
    it (Sophos, Zscaler, Fortinet, Palo Alto, …). Ask IT to exclude
    `api.themoviedb.org` and `image.tmdb.org`, or set `TMDB_CA_BUNDLE` in `.env`
    to the proxy's CA certificate.
  - **A hard block.** Some gateways refuse TLS to specific hosts outright rather
    than re-signing it, and nothing local can fix that — the connection never
    completes, so there is no certificate to trust. A CA bundle will not help.
    This is the case the relay exists for; see below.

  Either way the app still runs; tiles fall back to a placeholder. A different
  network (phone hotspot) is the quickest way to confirm.
- **Images load, metadata doesn't** → the key is wrong or expired.

To confirm from a terminal:

```bash
python -c "import tmdb_client as t; print(t.probe(), t.route(), t.image_route())"
```

### When the network blocks TMDB outright

When the direct route fails, `tmdb_client` falls back to two public services:
`r.jina.ai` for API responses, and `images.weserv.nl` for poster and backdrop
images. Both are tried in order and both are free, which also means they
rate-limit — the occasional slow lookup is expected. Responses are cached to
`tmdb_cache.pkl` for 30 days, so each title is fetched at most once per month.

**Your API key travels in the relay's request URL, so the relay operator can read
it.** That is acceptable for a local project and not for a shared or public
deployment. Set `TMDB_RELAY=off` in `.env` to refuse the relay and be told about
the block instead, or `TMDB_RELAY=only` to skip the doomed direct attempt. If
you have been running with the relay on, rotate your key at
<https://www.themoviedb.org/settings/api>.

## 🎨 Interface

Dark and light themes, switchable from the sidebar. The choice is stored in the
URL (`?theme=light`), so it survives a refresh. The **Recommend** button takes
its colour from the active palette rather than being hard-coded, so it stays
legible in both.

Posters are a responsive grid and **each tile's title is the button** that opens
the details dialog — there is no separate row of controls to line up with the
artwork. Titles the catalogue stores more than once (remakes, re-releases) get
their own row, because the TF-IDF ranking tends to bury them.

The grid flex-wraps rather than holding a fixed column count, so a phone shows
three tiles per row and a desktop shows six with no server-side guess about the
viewport. Below 768px the hero shrinks, the tap targets grow to 3.25rem, and text
inputs are held at 16px so iOS does not zoom when a field is focused.

Type a movie name, press **Recommend** (or Enter). The search is inside a form,
so the app no longer re-ranks on every keystroke.

Styling lives in `netflix_theme.py` and is scoped to `nf-` classes plus the
`st-key-*` classes Streamlit derives from `st.container(key=...)`, so it does not
depend on Streamlit's internal `data-testid` values.

## 🧪 Tests

```bash
python -m pytest tests/ -v     # 55 tests, no network or API key needed
```

## 🔒 Security

`.env` was committed in this repository's history and has since been purged with
`git filter-repo --path .env --invert-paths`; `raw.githubusercontent.com/.../.env`
now returns 404. **The old key must still be rotated** at
<https://www.themoviedb.org/settings/api> — removing it from history does not
invalidate a key that was public. `.env` is gitignored, and `.env.example`
documents every variable.

## 🚀 Deployed Link & Deployment

### GitHub Repository
**https://github.com/wd369018/movie-recommendation-system**

### Quick Deploy Options (pick one)

---

#### 1. **Streamlit Community Cloud** (free, 2 min setup, no Docker)
1. Push to GitHub (done — repo above)
2. Go to **[share.streamlit.io](https://share.streamlit.io/)** → Sign in with GitHub
3. "New app" → Select `wd369018/movie-recommendation-system`, branch `main`, file `app.py`
4. Advanced settings → **Secrets**:
   ```toml
   TMDB_API_KEY = "your_rotated_key_here"
   TMDB_RELAY = "auto"
   TMDB_LANG = "en-US"
   ```
5. Deploy → you get `https://movie-recommendation-system-<hash>.streamlit.app`

> ⚠️ **Limit**: 1 GB RAM, no persistent disk (cache resets on redeploy), cold start ~30 s.
> Good for demos.

---

#### 2. **Render / Railway / Fly.io** (persistent disk, stable URL, ~5 min)
Add a `Dockerfile` to the repo root:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHERUSAGESTATS=false
CMD ["streamlit", "run", "app.py"]
```

**Render:**
1. New → Web Service → Connect GitHub repo
2. Build: `docker build -t app .` (auto-detected from Dockerfile)
3. Add **Disk** → Mount path `/app` → 1 GB (for `tmdb_cache.pkl`)
4. Env vars: `TMDB_API_KEY`, `TMDB_RELAY=auto`
5. Deploy → `https://movie-recommendation-system.onrender.com`

**Railway:**
```bash
railway login
railway init
railway add --dockerfile
railway variables set TMDB_API_KEY=xxx TMDB_RELAY=auto
railway up
```

**Fly.io:**
```bash
fly launch --dockerfile
fly secrets set TMDB_API_KEY=xxx TMDB_RELAY=auto
fly volumes create tmdb_cache --size 1
fly deploy
```

---

#### 3. **Your own VM / VPS** (full control, cheapest at scale)
```bash
# On the server (Ubuntu/Debian)
sudo apt update && sudo apt install -y python3-venv nginx
git clone https://github.com/wd369018/movie-recommendation-system
cd movie-recommendation-system
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Pre-warm cache (run once, then weekly via cron)
TMDB_API_KEY=xxx .venv/bin/python prewarm_tmdb.py --top 100 --workers 4

# systemd service (/etc/systemd/system/flixfind.service)
[Unit]
Description=FLIXFIND Movie Recommender
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/movie-recommendation-system
Environment=TMDB_API_KEY=xxx
Environment=TMDB_RELAY=auto
ExecStart=/home/ubuntu/movie-recommendation-system/.venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=on-failure

[Install]
WantedBy=multi-user.target

# nginx reverse proxy (port 80/443 → 8501)
sudo certbot --nginx -d yourdomain.com
sudo systemctl enable --now flixfind
```

---

### Pre-deploy Checklist
- [ ] **Rotate TMDB key** at <https://www.themoviedb.org/settings/api> (old one was public)
- [ ] Add `TMDB_API_KEY` to platform secrets/env (never in code)
- [ ] Set `TMDB_RELAY=auto` (lets the app bypass network blocks)
- [ ] Run `prewarm_tmdb.py` locally or in CI to seed `tmdb_cache.pkl` (makes first loads instant)
- [ ] For Render/Railway/Fly: attach a **persistent volume** at `/app` so the cache survives redeploys

---

### Current Status
- ✅ Code pushed to GitHub (`main` branch, commit `9cd502f`)
- ✅ All 110 tests passing
- ✅ Server health check: `http://localhost:8501/_stcore/health` → 200
- ⏳ **Live URL**: Deploy via one of the options above — takes 5–10 min
