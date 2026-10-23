from datetime import date
import pytest
import service


def test_config_lists_31_delivery_days():
    c = service.config()
    assert len(c["delivery_dates"]) == 31
    assert c["delivery_dates"][0] == "2026-01-02" and c["delivery_dates"][-1] == "2026-02-01"


def test_day_view_has_48_points_and_cutoff_before_delivery():
    v = service.day_view(date(2026, 1, 10), 9, 0)
    assert len(v["points"]) == 48
    assert v["decision_cutoff_utc"].startswith("2026-01-09T09:00")
    assert v["forecast_published_to"] <= v["decision_cutoff_utc"]


def test_day_view_unknown_date_raises():
    with pytest.raises(LookupError):
        service.day_view(date(2025, 6, 1), 9, 0)


def test_earlier_cutoff_never_uses_newer_forecast():
    late = service.day_view(date(2026, 1, 10), 12, 0)["forecast_published_to"]
    early = service.day_view(date(2026, 1, 10), 6, 0)["forecast_published_to"]
    assert early <= late


def test_metrics_and_distribution_are_consistent():
    m = service.metrics_view(9, 0, None, None)
    assert m["summary"]["n"] == 1488 and len(m["by_hour"]) == 24 and len(m["by_day"]) == 31
    dist = service.error_distribution(9, 0, 500, None, None)
    assert sum(b["count"] for b in dist["bins"]) == 1488


def test_horizon_error_shrinks_closer_to_delivery():
    b = service.horizon_view(12)["buckets"]
    assert b[0]["mae_mw"] < b[-1]["mae_mw"]
