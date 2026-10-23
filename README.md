# UK Wind Forecast Dashboard

A web app for a UK energy utility's day-ahead power buying team. It answers two questions:

1. **What wind forecast did I actually have when I had to decide?** (the latest forecast published before the day-ahead decision deadline)
2. **How accurate are those forecasts?** (quantified in MW, with a recommended buffer)

Scope: national-level wind generation from Elexon only (FUELHH actuals, WINDFOR forecasts), for purchase decisions made in **January 2026** (delivery days 2 Jan to 1 Feb 2026).

- **Live app:** `https://zxcvbnm-179y.onrender.com/`

> **AI tools disclosure:** This project was built with the assistance of an AI tool (Claude, by Anthropic) for planning, code generation, and documentation. I reviewed, ran, and tested the code myself.

---

## 1. Quick start

### Option A: Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:8000. FastAPI serves both the API (`/api/...`) and the built React dashboard. API docs are at http://localhost:8000/docs.

### Option B: Run locally without Docker

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest                               # run the tests
uvicorn main:app --reload            # http://127.0.0.1:8000
```

Frontend (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to port 8000)
```

### Refreshing the data (optional)

The repo ships with a data snapshot, so this is not needed to run the app.

```bash
cd backend
python ingest.py
```

---

## 2. Repository layout

```
.
├── backend/
│   ├── ingest.py            Downloads Elexon data (FUELHH wind, WINDFOR) into CSV files
│   ├── analysis.py          Core logic: decision cutoff, forecast selection, error metrics
│   ├── service.py           Builds JSON responses from the analysis; caches datasets
│   ├── main.py              FastAPI routes + input validation; serves the built frontend
│   ├── test_analysis.py     Unit tests for the time and selection logic
│   ├── test_service.py      Tests for response shapes and consistency
│   ├── requirements.txt     Python dependencies
│   └── data/
│       ├── actuals.csv      Half-hourly actual wind (MW)
│       └── forecasts.csv    Hourly wind forecasts with publishTime (MW)
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js       Dev server proxy: /api -> http://127.0.0.1:8000
│   └── src/
│       ├── main.jsx         React entry point
│       ├── App.jsx          App shell + three views (Decision, Accuracy, Risk)
│       ├── api.js           All backend calls in one place
│       └── index.css        Styles
├── Dockerfile               Multi-stage: build React, then Python image serving both
├── docker-compose.yml       One-command local start
├── .dockerignore
├── .gitignore
└── README.md
```

---

## 3. Architecture

```
 Elexon Insights API  (FUELHH, WINDFOR)
         |   one-time download
         v
     ingest.py  -->  backend/data/*.csv   (committed snapshot)
                              |
     +------------------------+---------------------------+
     |  Python backend (FastAPI)                           |
     |   analysis.py  pure pandas logic (cutoff, select,   |
     |                metrics)                             |
     |   service.py   JSON builders + caching              |
     |   main.py      HTTP routes + validation             |
     +------------------------+---------------------------+
                              |  JSON over /api/*
                              v
              React + Recharts dashboard (Vite)

   Docker: one image; FastAPI also serves the built React files
```

**Key decision, snapshot data:** January 2026 is historical and does not change, so the data is downloaded once and shipped with the app. The deployed app does not depend on Elexon's availability or rate limits, responses are fast, and the demo is reliable. Re-running `ingest.py` refreshes it.

---

## 4. Design

### Backend layers

| Layer | File | Responsibility |
|---|---|---|
| Logic | `analysis.py` | Time rules and statistics. No web code, so it is easy to test and reuse. |
| Service | `service.py` | Turns analysis output into JSON, handles caching (`lru_cache`). |
| HTTP | `main.py` | Routes, parameter validation (hour 0-23, minute 0-59, dates), 404 for unknown dates. |

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/config` | Date range, default cutoff, delivery days, typical forecast publish times |
| `GET /api/day?date=YYYY-MM-DD` | The decision-time forecast for one delivery day, its publish time, and the actuals |
| `GET /api/metrics` | Summary metrics, plus breakdown by hour of day and by delivery day |
| `GET /api/error-distribution` | Error histogram and percentiles |
| `GET /api/horizon` | Accuracy of all forecasts by lead time (hours between publish and target) |

Endpoints that depend on the decision deadline accept `cutoff_hour` and `cutoff_minute` (London time, on the day before delivery).

### Frontend

Three views that follow the client's questions:

1. **Decision view:** pick a delivery day; see the deadline, which forecast was usable, and the forecast curve. A checkbox reveals the actuals.
2. **Forecast accuracy:** MAE, RMSE, bias, MAPE cards; error by delivery day and by hour of day.
3. **Risk and buffer:** a plain-language summary of the extra MW that would have covered 90% and 95% of over-forecasts, an error histogram, and error versus forecast lead time.

The decision deadline can be changed in the UI so the client can see how much it matters.

---

## 5. Analysis

### The core problem

For each target time there are many forecasts, published at different times. A buyer deciding the day before can only use forecasts that already existed at the deadline. Using later (more accurate) forecasts would overstate accuracy.

### Method

1. **Deadline:** for delivery day D, the deadline is **09:00 London time on D-1** (configurable). Time zone handling uses `Europe/London`, so daylight saving time is handled correctly.
2. **Selection:** for each target time, take the forecast with the **latest `publishTime` at or before the deadline**. A forecast published exactly at the deadline is allowed.
3. **Join:** match with FUELHH `WIND` actuals. WINDFOR is hourly and FUELHH is half-hourly, so each hourly forecast is applied to both half-hours of that hour.
4. **Error sign:** `error = forecast - actual`. Positive means the forecast was too high (wind lower than expected), which is the shortfall risk for a buyer.

### Metrics

MAE, RMSE, bias (mean error), MAPE, P50/P90/P95 of absolute error, and a **buffer**: the P90 and P95 of the (over-forecast) error, i.e. the extra MW that would have covered shortfalls 90% / 95% of the time.

### Results (09:00 deadline, 1,488 half-hours, 31 delivery days)

| Metric | Value |
|---|---|
| Mean actual wind | ~11,284 MW |
| MAE | ~2,042 MW |
| RMSE | ~2,509 MW |
| Bias | +1,748 MW (forecasts too high on average) |
| P95 absolute error | ~5,310 MW |
| Buffer for 90% / 95% cover | ~4,140 / ~5,310 MW |

Findings:

- Forecasts follow the shape of actual wind closely (correlation about 0.93) but run consistently high in this period.
- Forecasts published closer to delivery are more accurate. The day-ahead buyer has to use the older, less accurate ones.
- The choice of deadline changes which forecast is usable, which is why it is configurable.

---

## 6. Assumptions

1. **Decision deadline of 09:00 London time on D-1 is an assumption.** The brief only says decisions are made one day before delivery. Verify the real day-ahead auction gate-closure time before relying on it; it is a single configurable value.
2. Forecasts are hourly and actuals half-hourly; hourly forecasts are applied to both half-hours.
3. Only the national-level wind series is used; no other data, as specified.
4. "January 2026 decisions" means delivery days 2 Jan to 1 Feb 2026 (decided 1 Jan to 31 Jan). Forecasts published from 31 Dec 2025 are downloaded to cover this.
5. Actuals for 2 Feb that appear in the download are excluded as out of scope.

## 7. Limitations and next steps

- One month of data and one national series. The buffer covers wind forecast error only, not demand or other sources of uncertainty.
- The persistent positive bias deserves investigation (for example, whether the forecast and the metered actuals cover the same set of wind generation). This has not been verified here.
- MAPE is unstable when wind output is low, so MAE and RMSE are the main figures.
- Possible next steps: scheduled data refresh, seasonal and wind-level quantile buffers, forecast bias monitoring, authentication.

---

## 8. Development practices

- **Tests on the risky logic:** deadline calculation (including British Summer Time), inclusion of a forecast published exactly at the deadline, exclusion of later forecasts, hourly-to-half-hourly handling, error and metric calculation, response shapes and consistency. Run with `pytest` in `backend/`.
- **Separation of concerns:** logic, service and HTTP layers are independent.
- **Explicit, configurable assumptions** documented above.
- **Input validation** at the API boundary.
- **Reproducible builds:** multi-stage Dockerfile, dependency files, `.gitignore` and `.dockerignore`.
- **Single source for API calls** in the frontend (`api.js`).
- **AI use disclosed** (see top of this file).

---

## 9. Deployment

`<ADD STEPS AND LIVE LINK ONCE DEPLOYED>`

The app is a single container listening on `$PORT` (default 8000), so it can run on any container platform.

## 10. Data source

Elexon BMRS / Insights API: datasets FUELHH (fuel type `WIND`) and WINDFOR.
