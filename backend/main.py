# """FastAPI app: thin HTTP layer over service.py."""
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import service

app = FastAPI(
    title="Wind Forecast Accuracy API",
    description="Decision-time wind forecasts vs actuals for UK day-ahead buying (Jan 2026).",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

CUTOFF_HOUR = Query(9, ge=0, le=23, description="Decision cutoff hour on D-1, London time")
CUTOFF_MINUTE = Query(0, ge=0, le=59, description="Decision cutoff minute")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def get_config():
    return service.config()


@app.get("/api/day")
def get_day(date: date, cutoff_hour: int = CUTOFF_HOUR, cutoff_minute: int = CUTOFF_MINUTE):
    """Forecast available at the cutoff for one delivery day, plus the actuals."""
    try:
        return service.day_view(date, cutoff_hour, cutoff_minute)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/metrics")
def get_metrics(
    start: date | None = None, end: date | None = None,
    cutoff_hour: int = CUTOFF_HOUR, cutoff_minute: int = CUTOFF_MINUTE,
):
    return service.metrics_view(cutoff_hour, cutoff_minute, start, end)


@app.get("/api/error-distribution")
def get_error_distribution(
    bin_width: int = Query(500, ge=50, le=5000),
    start: date | None = None, end: date | None = None,
    cutoff_hour: int = CUTOFF_HOUR, cutoff_minute: int = CUTOFF_MINUTE,
):
    return service.error_distribution(cutoff_hour, cutoff_minute, bin_width, start, end)


@app.get("/api/horizon")
def get_horizon(bucket_hours: int = Query(6, ge=1, le=24)):
    """Accuracy of all forecasts by lead time (how far ahead they were published)."""
    return service.horizon_view(bucket_hours)



# Serve the built React app when present (inside Docker it is copied to ./static)
STATIC = Path(__file__).parent / "static"
if (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")