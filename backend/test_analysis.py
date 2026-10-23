import pandas as pd
from analysis import cutoff_for, select_forecast, build_dataset, metrics


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_cutoff_is_previous_day_0900_london():
    c = cutoff_for(pd.Series([ts("2026-01-10 12:00")]))
    assert c.iloc[0] == ts("2026-01-09 09:00")  # January: London == UTC


def test_summer_cutoff_respects_bst():
    c = cutoff_for(pd.Series([ts("2026-07-10 12:00")]))
    assert c.iloc[0] == ts("2026-07-09 08:00")  # 09:00 BST = 08:00 UTC


def test_latest_forecast_before_cutoff_is_chosen_and_later_ignored():
    f = pd.DataFrame({
        "startTime": [ts("2026-01-10 12:00")] * 4,
        "publishTime": [ts("2026-01-09 04:30"), ts("2026-01-09 07:30"),
                        ts("2026-01-09 09:30"), ts("2026-01-10 02:30")],
        "generation": [100, 200, 300, 400],
    })
    sel = select_forecast(f)
    assert sel["forecast"].iloc[0] == 200  # 09:30 and later were not available


def test_forecast_published_exactly_at_cutoff_is_allowed():
    f = pd.DataFrame({"startTime": [ts("2026-01-10 12:00")],
                      "publishTime": [ts("2026-01-09 09:00")], "generation": [123]})
    assert select_forecast(f)["forecast"].iloc[0] == 123


def test_hourly_forecast_applies_to_both_half_hours_and_errors_are_correct():
    f = pd.DataFrame({"startTime": [ts("2026-01-10 12:00")],
                      "publishTime": [ts("2026-01-09 07:30")], "generation": [1000]})
    a = pd.DataFrame({"startTime": [ts("2026-01-10 12:00"), ts("2026-01-10 12:30")],
                      "generation": [900, 1200]})
    df = build_dataset(a, f)
    assert list(df["error"]) == [100, -200]
    m = metrics(df)
    assert m["mae_mw"] == 150 and m["bias_mw"] == -50
