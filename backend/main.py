import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from scraper import scrape_store
from mapper import map_to_model
from excel_export import export_xlsx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(BASE_DIR, "..")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    url: str


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
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


# Serve frontend
frontend_dir = os.path.join(PROJECT_DIR, "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
