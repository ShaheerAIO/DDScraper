# DoorDash Menu Scraper

## Overview
A web app that scrapes a DoorDash store's menu and exports it into a 14-sheet Excel
workbook matching a fixed POS import schema (`exampleSchema.xlsx`). A user pastes a
DoorDash store URL into a simple web page; the backend loads the page with a headless
browser, extracts menu data, normalizes it, and returns a downloadable `.xlsx`.
A JSON-only API is also exposed for programmatic use.

## Tech Stack
- **Language:** Python 3.11 (backend), vanilla HTML/CSS/JS (frontend — no build step).
- **Backend framework:** FastAPI 0.115.6, served by Uvicorn 0.34.0.
- **Scraping:** Playwright 1.49.1 (headless Chromium).
- **Excel:** openpyxl 3.1.5.
- **Deploy:** Docker (`python:3.11-slim`) on Railway.

## Architecture
Request flow: `frontend` posts a store URL to the FastAPI backend → `scraper.py`
loads the DoorDash page in headless Chromium and extracts raw menu data →
`mapper.py` normalizes that raw data into the 14-section model → `excel_export.py`
fills the `exampleSchema.xlsx` template and writes `output.xlsx`, which is returned
as a file download.

Three-stage pipeline:
1. **Scrape** (`scraper.py`): Two extraction strategies, tried in order:
   - **RSC** (preferred): parses Next.js React Server Components Flight payload
     (`self.__next_f.push([...])`) to pull `itemLists`. Gives richer data including
     an `imageUrl` per item. RSC `$L`-style references are stripped before JSON parse.
   - **ld+json** (fallback): reads `script[type="application/ld+json"]` schema.org
     `Menu`/`hasMenuSection` blocks (name/description/price only).
   - Store name comes from the ld+json `Restaurant` block.
   - Returns `{store_id, store_name, source: "rsc"|"ld_json", item_lists | sections}`.
2. **Map** (`mapper.py`): `map_to_model()` dispatches on `source` to `_map_rsc` or
   `_map_ld_json`. Builds Menu / Category / Item / Category Items rows; dedupes items
   (by DoorDash item id for RSC, by name for ld+json); all other 10 sheets are emitted
   empty. Output keys exactly match the Excel sheet names.
3. **Export** (`excel_export.py`): `SHEET_COLUMNS` maps each sheet name to an ordered
   list of model keys. Loads the template, deletes all data rows (keeps the header
   row), and writes the model rows back.

The FastAPI app also mounts `frontend/` as static files at `/`, so backend and UI are
served from the same origin.

## Key Files & Entry Points
- `/Users/shaheerhasnain/DD Scraper Website/backend/main.py` — FastAPI app and entry
  point. Defines routes, CORS, in-memory rate limiting; mounts the frontend.
- `/Users/shaheerhasnain/DD Scraper Website/backend/scraper.py` — Playwright scraping
  (`scrape_store`, RSC + ld+json extraction).
- `/Users/shaheerhasnain/DD Scraper Website/backend/mapper.py` — Normalizes raw scrape
  output into the 14-section model (`map_to_model`).
- `/Users/shaheerhasnain/DD Scraper Website/backend/excel_export.py` — Fills the Excel
  template (`export_xlsx`, `SHEET_COLUMNS`).
- `/Users/shaheerhasnain/DD Scraper Website/backend/requirements.txt` — Python deps.
- `/Users/shaheerhasnain/DD Scraper Website/frontend/index.html` — Single-page UI.
- `/Users/shaheerhasnain/DD Scraper Website/frontend/app.js` — Form submit → POST
  `/api/scrape` → triggers file download.
- `/Users/shaheerhasnain/DD Scraper Website/frontend/styles.css` — Styling.
- `/Users/shaheerhasnain/DD Scraper Website/exampleSchema.xlsx` — Excel template
  (14 sheets); the source of truth for sheet/column layout. Required at runtime.
- `/Users/shaheerhasnain/DD Scraper Website/output.xlsx` — Generated output (gitignored,
  overwritten on each scrape).
- `/Users/shaheerhasnain/DD Scraper Website/Dockerfile` — Container build (installs
  Playwright Chromium + system libs).
- `/Users/shaheerhasnain/DD Scraper Website/railway.toml` — Railway deploy config.

### HTTP API (defined in `main.py`)
- `GET  /api/health` — `{"status": "ok"}` (Railway healthcheck path).
- `POST /api/scrape` — body `{"url": "..."}`; returns the `.xlsx` file.
- `POST /api/scrape-json` — same input; returns the normalized model as JSON.
- `POST /api/normalize` — body is a raw `scrape_store()`-shaped payload; returns the
  normalized model JSON (skips scraping).

## Build / Run / Test
No README, Makefile, or test suite exists. Commands below are derived from
`requirements.txt`, the `Dockerfile`, and import paths.

**Local (run from the project root):**
```sh
pip install -r backend/requirements.txt
playwright install chromium
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Then open http://localhost:8000/ (the frontend) or call the API on the same port.
Note: `main.py` resolves `exampleSchema.xlsx` relative to the project root (one level
above `backend/`), so run uvicorn from the project root.

**Docker:**
```sh
docker build -t dd-scraper .
docker run -p 8000:8000 dd-scraper
```
The container runs `python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}`.

**Deploy:** Railway uses the Dockerfile (`railway.toml`); healthcheck `/api/health`,
restart on failure (max 3 retries). Railway provides `PORT`.

## Conventions & Gotchas
- **No tests, no linter config, no CI.** Verification is manual.
- **Template-driven schema:** `excel_export.SHEET_COLUMNS`, the model keys in
  `mapper.py`, and the sheets/columns in `exampleSchema.xlsx` must stay in sync. The
  exporter only deletes/rewrites data rows; the template (headers, formatting) is
  preserved. Changing the schema means updating all three together.
- **Scraping is fragile by nature:** DoorDash markup changes can break RSC extraction
  (it parses the `__next_f` Flight payload with regex and bracket-matching). The RSC
  reference-stripping regex (`"\$L?[0-9a-f]+"` → `"__ref__"`) is a heuristic. ld+json
  is the fallback; if both fail, the scrape raises (HTTP 422).
- **Only 4 of 14 sheets are populated** (Menu, Category, Item, Category Items); all
  modifier/allergen/tag sheets are intentionally emitted empty.
- **Hardcoded defaults** in `mapper.py`: button color `#FCA98F`, category color
  `#FF7B42`, `stationIds="1"`, `saleCategory="Food Sales"`, limits 1–999, etc.
- **Prices:** `_parse_dd_price` strips `$`/`,` and tolerates DoorDash's `$$15.68`
  display format; unparseable prices fall back to `0`.
- **Rate limiting** is in-memory per client IP (default 10/min, `RATE_LIMIT_PER_MINUTE`
  env var), respecting `X-Forwarded-For`. It is per-process and resets on restart —
  not suitable for multi-instance scaling.
- **CORS** defaults to `*`; override via `ALLOWED_ORIGINS` (comma-separated).
- **Shared output file:** every scrape writes the same `output.xlsx` at the project
  root — concurrent scrapes can race on that file.
- The 5s `wait_for_timeout` plus page load is why the UI warns the scrape takes
  ~15-30s.
