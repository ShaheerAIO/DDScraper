import os
import sys
import time
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Allow imports from backend/ dir whether run as module or directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import scrape_store
from mapper import map_to_model
from excel_export import export_xlsx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(BASE_DIR, "..")

app = FastAPI(title="DoorDash Menu Scraper API")

# CORS — configurable via env, defaults to all origins for public access
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# --- Simple in-memory rate limiter ---
_rate_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
RATE_WINDOW_SECONDS = 60.0


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    timestamps = _rate_store[ip]
    _rate_store[ip] = [t for t in timestamps if now - t < RATE_WINDOW_SECONDS]
    if len(_rate_store[ip]) >= RATE_LIMIT_PER_MINUTE:
        return False
    _rate_store[ip].append(now)
    return True


class ScrapeRequest(BaseModel):
    url: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest, request: Request):
    """Scrape a DoorDash store URL and return an Excel file."""
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")

    try:
        raw = await scrape_store(req.url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        model = map_to_model(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mapping error: {e}")

    template_path = os.path.join(PROJECT_DIR, "exampleSchema.xlsx")
    out_path = os.path.join(PROJECT_DIR, "output.xlsx")

    try:
        export_xlsx(model, template_path, out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel export error: {e}")

    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"doordash-menu-{model.get('store_id', 'export')}.xlsx",
    )


@app.post("/api/scrape-json")
async def scrape_json(req: ScrapeRequest, request: Request):
    """Scrape a DoorDash store URL and return normalized menu data as JSON.

    Response schema:
    {
        "store_id": string,
        "Menu": [...],
        "Category": [...],
        "Item": [...],
        "Item Modifiers": [],
        "Category ModifierGroups": [],
        "Category Modifiers": [],
        "Category Items": [...],
        "Item Modifier Group": [],
        "Modifier Group": [],
        "Modifier": [],
        "Modifier Option": [],
        "Modifier ModifierOptions": [],
        "Allergen": [],
        "Tag": []
    }
    """
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")

    try:
        raw = await scrape_store(req.url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        model = map_to_model(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mapping error: {e}")

    return JSONResponse(content=model)


@app.post("/api/normalize")
async def normalize(payload: dict, request: Request):
    """Normalize a raw scraper output payload into the menu model.

    Accepts the scrape_store() output structure:
    {
        "store_id": string,
        "store_name": string | null,
        "source": "rsc" | "ld_json",
        "item_lists": [...]  // for source=rsc
        "sections": [...]    // for source=ld_json
    }

    Returns the same normalized JSON as /api/scrape-json.
    """
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")

    try:
        model = map_to_model(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mapping error: {e}")

    return JSONResponse(content=model)


# Serve frontend
frontend_dir = os.path.join(PROJECT_DIR, "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
