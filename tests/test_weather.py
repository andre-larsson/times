"""The weather box: Open-Meteo's columns condensed for the front page (no network)."""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from newsroom import generate as gen
from newsroom import store
from newsroom.config import load_config
from newsroom.sources import fetch_all, weather
from tests.test_pipeline import NOW, FakeClient, _harvest

CFG = {"enabled": True, "place": "Sample City", "latitude": 0, "longitude": 0, "hours": [9, 12, 15, 18], "days": 2}


def _open_meteo() -> dict:
    days = ["2026-11-03", "2026-11-04", "2026-11-05"]
    hours = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    return {
        "daily": {"time": days, "weather_code": [61, 1, 71], "temperature_2m_max": [6.6, 4.5, 2.6],
                  "temperature_2m_min": [1.6, -0.6, -2.4], "precipitation_sum": [2.38, 0.0, 1.2],
                  "precipitation_probability_max": [70, 5, 55], "wind_speed_10m_max": [6.4, 3.0, 4.1],
                  "sunrise": [f"{d}T07:12" for d in days], "sunset": [f"{d}T15:49" for d in days]},
        "hourly": {"time": hours, "temperature_2m": [float(i % 24) / 3 for i in range(len(hours))],
                   "weather_code": [3] * len(hours), "precipitation_probability": [20] * len(hours)},
    }


def test_condense_today_hours_ahead_and_next_days():
    now = dt.datetime(2026, 11, 3, 10, 5, tzinfo=ZoneInfo("Europe/Stockholm"))
    w = weather.condense(_open_meteo(), CFG, now)
    assert w["place"] == "Sample City"
    t = w["today"]
    assert (t["high"], t["low"], t["condition"], t["precip_chance"], t["precip_mm"], t["wind_ms"]) == \
        (7, 2, "Light rain", 70, 2.4, 6)
    assert (t["sunrise"], t["sunset"]) == ("07:12", "15:49")
    assert [h["time"] for h in w["hours"]] == ["12:00", "15:00", "18:00"]      # 09:00 has passed
    assert [h["temp"] for h in w["hours"]] == [4, 5, 6] and w["hours"][0]["condition"] == "Cloudy"
    assert [(d["date"], d["high"], d["low"], d["condition"]) for d in w["days"]] == \
        [("2026-11-04", 4, -1, "Mostly clear"), ("2026-11-05", 3, -2, "Light snow")]


def test_a_failing_forecast_never_stops_the_run():
    cfg = load_config()
    cfg = {**cfg, "sources": {}, "weather": {**CFG}}
    h = fetch_all(cfg, FakeClient({}), NOW)                     # FakeClient refuses the unexpected fetch
    assert h.weather is None
    assert [(s.name, s.ok) for s in h.status] == [("Weather (Open-Meteo, Sample City)", False)]


def test_forecast_is_fetched_for_the_configured_place():
    cfg = {**load_config(), "sources": {}, "weather": {**CFG}}
    h = fetch_all(cfg, FakeClient({weather.API: _open_meteo()}), NOW)
    assert h.weather and h.weather["today"]["date"] == NOW.astimezone(ZoneInfo("Europe/Stockholm")).date().isoformat()


def test_the_edition_carries_the_forecast(tmp_path, monkeypatch):
    def harvest(cfg, client, now, itad_key=None):
        h = _harvest()
        h.weather = weather.condense(_open_meteo(), CFG, now.astimezone(ZoneInfo("Europe/Stockholm")))
        return h

    monkeypatch.setattr(gen, "fetch_all", harvest)
    r = gen.generate(load_config(), tmp_path, "links", now=NOW, env={}, client=FakeClient({}))
    assert r.published
    saved = json.loads(store.edition_path(tmp_path, r.edition_id).read_text())
    assert saved["weather"]["place"] == "Sample City" and saved["weather"]["days"]
