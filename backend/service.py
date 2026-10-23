"""Business logic behind the API. Returns plain JSON-friendly dicts."""
import json
from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd

import analysis as an


@lru_cache(maxsize=1)
def _raw():
    return an.load_data()


@lru_cache(maxsize=64)
def dataset(hour: int, minute: int) -> pd.DataFrame:
    actuals, forecasts = _raw()
    return an.build_dataset(actuals, forecasts, hour, minute)


def _records(df: pd.DataFrame) -> list:
    """DataFrame -> list of dicts; NaN becomes null, timestamps become ISO strings."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _clean(obj):
    return json.loads(json.dumps(obj, default=str, allow_nan=True).replace("NaN", "null"))


def _in_range(df, start: date | None, end: date | None):
    if start:
        df = df[df["delivery_date"] >= start]
    if end:
        df = df[df["delivery_date"] <= end]
    return df


def config() -> dict:
    _, forecasts = _raw()
    pub = forecasts["publishTime"].dt.strftime("%H:%M").value_counts()
    return {
        "scope_start": an.SCOPE_START.isoformat(),
        "scope_end": an.SCOPE_END.isoformat(),
        "default_cutoff_hour": an.CUTOFF_HOUR,
        "default_cutoff_minute": an.CUTOFF_MINUTE,
        "timezone": an.LONDON,
        # publish slots with at least 1% of all forecasts (ignores rare ad-hoc ones)
        "typical_publish_times_utc": sorted(pub[pub > len(forecasts) * 0.01].index.tolist()),
        "delivery_dates": [d.isoformat() for d in sorted(dataset(an.CUTOFF_HOUR, an.CUTOFF_MINUTE)["delivery_date"].unique())],
    }


def day_view(delivery_date: date, hour: int, minute: int) -> dict:
    df = dataset(hour, minute)
    d = df[df["delivery_date"] == delivery_date]
    if d.empty:
        raise LookupError(f"No data for delivery date {delivery_date}")
    points = d[["startTime", "forecast", "actual"]]
    return {
        "delivery_date": delivery_date.isoformat(),
        "decision_cutoff_utc": d["cutoff"].min().isoformat(),
        "forecast_published_from": d["publishTime"].min().isoformat(),
        "forecast_published_to": d["publishTime"].max().isoformat(),
        "forecast_total_mwh": float(d["forecast"].sum() / 2),   # half-hourly MW -> MWh
        "actual_total_mwh": float(d["actual"].sum() / 2),
        "metrics": _clean(an.metrics(d)),
        "points": _records(points),
    }


def metrics_view(hour: int, minute: int, start: date | None, end: date | None) -> dict:
    d = _in_range(dataset(hour, minute), start, end)
    by_day = an.metrics_by_day(d)
    by_day["delivery_date"] = by_day["delivery_date"].astype(str)
    return {
        "cutoff": {"hour": hour, "minute": minute, "timezone": an.LONDON},
        "summary": _clean(an.metrics(d)),
        "by_hour": _records(an.metrics_by_hour(d)),
        "by_day": _records(by_day),
    }


def error_distribution(hour: int, minute: int, bin_width: int, start: date | None, end: date | None) -> dict:
    d = _in_range(dataset(hour, minute), start, end).dropna(subset=["error"])
    e = d["error"].to_numpy()
    lo = np.floor(e.min() / bin_width) * bin_width
    hi = np.ceil(e.max() / bin_width) * bin_width + bin_width
    counts, edges = np.histogram(e, bins=np.arange(lo, hi + bin_width, bin_width))
    return {
        "bin_width_mw": bin_width,
        "bins": [{"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)],
        "percentiles_mw": {f"p{p}": float(np.percentile(e, p)) for p in (5, 10, 25, 50, 75, 90, 95)},
        "note": "error = forecast - actual; positive = over-forecast (wind lower than expected)",
    }


def horizon_view(bucket_h: int) -> dict:
    actuals, forecasts = _raw()
    return {"bucket_hours": bucket_h, "buckets": _records(an.horizon_errors(actuals, forecasts, bucket_h))}
