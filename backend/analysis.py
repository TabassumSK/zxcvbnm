"""
Core analysis: which forecast did the buyer have at decision time, and how
accurate was it?
 
Rules (assumptions, all configurable):
 - Delivery day D is bought on day D-1, with a cutoff at CUTOFF_HOUR:CUTOFF_MINUTE
   London time (default 09:00).
 - For each target time, we use the forecast with the LATEST publishTime that is
   <= cutoff. Later (more accurate) forecasts are ignored: they were not available.
 - Forecasts are hourly, actuals half-hourly: an hourly forecast is applied to
   both half-hours of that hour.
 - error = forecast - actual  (positive = over-forecast, i.e. wind was lower than
   expected, so the buyer would be short and need extra power).
"""
from datetime import date
from pathlib import Path
 
import numpy as np
import pandas as pd
 
DATA = Path(__file__).parent / "data"
LONDON = "Europe/London"
CUTOFF_HOUR = 9
CUTOFF_MINUTE = 0
SCOPE_START = date(2026, 1, 2)   # first delivery day (decided on 1 Jan)
SCOPE_END = date(2026, 2, 1)     # last delivery day (decided on 31 Jan)
 
 
def load_data():
    actuals = pd.read_csv(DATA / "actuals.csv", parse_dates=["startTime"])
    forecasts = pd.read_csv(DATA / "forecasts.csv", parse_dates=["startTime", "publishTime"])
    return actuals, forecasts
 
 
def cutoff_for(start_times: pd.Series, hour=CUTOFF_HOUR, minute=CUTOFF_MINUTE) -> pd.Series:
    """Decision cutoff (UTC) for each target time: D-1 at hour:minute London time."""
    local_day = start_times.dt.tz_convert(LONDON).dt.tz_localize(None).dt.normalize()
    local_cutoff = local_day - pd.Timedelta(days=1) + pd.Timedelta(hours=hour, minutes=minute)
    return local_cutoff.dt.tz_localize(LONDON, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
 
 
def select_forecast(forecasts: pd.DataFrame, hour=CUTOFF_HOUR, minute=CUTOFF_MINUTE) -> pd.DataFrame:
    """For each target startTime, the latest forecast published at or before the cutoff."""
    f = forecasts.copy()
    f["cutoff"] = cutoff_for(f["startTime"], hour, minute)
    f = f[f["publishTime"] <= f["cutoff"]]
    f = f.sort_values(["startTime", "publishTime"]).groupby("startTime", as_index=False).last()
    return f.rename(columns={"generation": "forecast"})
 
 
def build_dataset(actuals, forecasts, hour=CUTOFF_HOUR, minute=CUTOFF_MINUTE) -> pd.DataFrame:
    """Actual vs decision-time forecast, one row per half-hour in scope."""
    sel = select_forecast(forecasts, hour, minute)[["startTime", "publishTime", "cutoff", "forecast"]]
    a = actuals.rename(columns={"generation": "actual"}).copy()
    a["hourStart"] = a["startTime"].dt.floor("h")
    df = a.merge(sel.rename(columns={"startTime": "hourStart"}), on="hourStart", how="left")
    df["delivery_date"] = df["startTime"].dt.tz_convert(LONDON).dt.date
    df = df[(df["delivery_date"] >= SCOPE_START) & (df["delivery_date"] <= SCOPE_END)]
    df["horizon_h"] = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600
    df["error"] = df["forecast"] - df["actual"]
    df["abs_error"] = df["error"].abs()
    return df.drop(columns=["hourStart"]).reset_index(drop=True)
 
 
def metrics(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["error"])
    if d.empty:
        return {"n": 0}
    return {
        "n": int(len(d)),
        "mean_actual_mw": float(d["actual"].mean()),
        "mae_mw": float(d["abs_error"].mean()),
        "rmse_mw": float(np.sqrt((d["error"] ** 2).mean())),
        "bias_mw": float(d["error"].mean()),
        "mape_pct": float((d["abs_error"] / d["actual"]).mean() * 100),
        "p50_abs_error_mw": float(d["abs_error"].quantile(0.50)),
        "p90_abs_error_mw": float(d["abs_error"].quantile(0.90)),
        "p95_abs_error_mw": float(d["abs_error"].quantile(0.95)),
        # Buffer: extra MW to cover over-forecasts (wind lower than forecast) X% of the time
        "buffer_p90_mw": float(max(d["error"].quantile(0.90), 0)),
        "buffer_p95_mw": float(max(d["error"].quantile(0.95), 0)),
    }
 
 
def metrics_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["error"]).copy()
    d["hour"] = d["startTime"].dt.tz_convert(LONDON).dt.hour
    return d.groupby("hour").agg(mae_mw=("abs_error", "mean"), bias_mw=("error", "mean")).reset_index()
 
 
def metrics_by_day(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["error"])
    return d.groupby("delivery_date").agg(
        mae_mw=("abs_error", "mean"), bias_mw=("error", "mean"), mean_actual_mw=("actual", "mean")
    ).reset_index()
 
 
if __name__ == "__main__":
    a, f = load_data()
    df = build_dataset(a, f)
    print(df.head(), "\nrows:", len(df), "missing forecast:", df["forecast"].isna().sum())
    print(metrics(df))
 
 
def horizon_errors(actuals, forecasts, bucket_h: int = 6) -> pd.DataFrame:
    """Accuracy of EVERY forecast vs lead time (hours between publish and target).
    Shows how forecasts improve as delivery approaches; only lead times >= 0."""
    a = actuals.rename(columns={"generation": "actual"}).copy()
    a["hourStart"] = a["startTime"].dt.floor("h")
    a["delivery_date"] = a["startTime"].dt.tz_convert(LONDON).dt.date
    a = a[(a["delivery_date"] >= SCOPE_START) & (a["delivery_date"] <= SCOPE_END)]
    f = forecasts.rename(columns={"startTime": "hourStart", "generation": "forecast"})
    d = a.merge(f, on="hourStart")
    d["horizon_h"] = (d["hourStart"] - d["publishTime"]).dt.total_seconds() / 3600
    d = d[d["horizon_h"] >= 0]
    d["error"] = d["forecast"] - d["actual"]
    d["abs_error"] = d["error"].abs()
    d["bucket_start"] = (d["horizon_h"] // bucket_h * bucket_h).astype(int)
    out = d.groupby("bucket_start").agg(
        mae_mw=("abs_error", "mean"), bias_mw=("error", "mean"), n=("error", "size")
    ).reset_index()
    out["bucket_end"] = out["bucket_start"] + bucket_h
    return out
 
