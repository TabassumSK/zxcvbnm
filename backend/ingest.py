"""
Downloads wind ACTUALS (FUELHH) and wind FORECASTS (WINDFOR) from Elexon
and saves them as CSV files in backend/data/.

Scope: decisions made in January 2026.
 - Delivery days: 2 Jan 2026 to 1 Feb 2026 (decision is made on the day before)
 - So we need forecasts published from 31 Dec 2025 to 31 Jan 2026
 - And actuals from 2 Jan 2026 to 1 Feb 2026
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)


def chunks(start: datetime, end: datetime, days: int):
    """Split a date range into smaller windows (the API limits range size)."""
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        yield cur, nxt
        cur = nxt


def get_json(url: str, params: dict) -> list[dict]:
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    # stream endpoints return a plain list; others wrap it in {"data": [...]}
    return data["data"] if isinstance(data, dict) else data


def fetch_actuals(start: datetime, end: datetime) -> pd.DataFrame:
    rows = []
    for a, b in chunks(start, end, 7):
        params = {
            "settlementDateFrom": a.strftime("%Y-%m-%d"),
            "settlementDateTo": b.strftime("%Y-%m-%d"),
            "fuelType": "WIND",
        }
        rows += get_json(f"{BASE}/FUELHH/stream", params)
        print(f"actuals {a.date()} -> {b.date()}: {len(rows)} rows so far")
    df = pd.DataFrame(rows)
    df = df[df["fuelType"] == "WIND"].copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df = df[["startTime", "generation"]].drop_duplicates("startTime")
    return df.sort_values("startTime").reset_index(drop=True)


def fetch_forecasts(start: datetime, end: datetime) -> pd.DataFrame:
    rows = []
    for a, b in chunks(start, end, 3):
        params = {
            "publishDateTimeFrom": a.strftime("%Y-%m-%dT%H:%MZ"),
            "publishDateTimeTo": b.strftime("%Y-%m-%dT%H:%MZ"),
        }
        rows += get_json(f"{BASE}/WINDFOR/stream", params)
        print(f"forecasts {a.date()} -> {b.date()}: {len(rows)} rows so far")
    df = pd.DataFrame(rows)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df = df[["startTime", "publishTime", "generation"]]
    df = df.drop_duplicates(["startTime", "publishTime"])
    return df.sort_values(["startTime", "publishTime"]).reset_index(drop=True)


if __name__ == "__main__":
    utc = timezone.utc
    actuals = fetch_actuals(
        datetime(2026, 1, 2, tzinfo=utc), datetime(2026, 2, 2, tzinfo=utc)
    )
    forecasts = fetch_forecasts(
        datetime(2025, 12, 31, tzinfo=utc), datetime(2026, 2, 1, tzinfo=utc)
    )
    actuals.to_csv(OUT / "actuals.csv", index=False)
    forecasts.to_csv(OUT / "forecasts.csv", index=False)
    print("\nACTUALS", actuals.shape, actuals["startTime"].min(), "->", actuals["startTime"].max())
    print("FORECASTS", forecasts.shape, forecasts["publishTime"].min(), "->", forecasts["publishTime"].max())
    print(actuals.head(), "\n", forecasts.head())