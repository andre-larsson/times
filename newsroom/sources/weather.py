"""The front page's weather box: today's forecast from Open-Meteo (no key; data CC BY 4.0, credited in the box)."""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from ..http import Client

API = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes, as Open-Meteo documents them
CONDITIONS = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorms", 96: "Thunder and hail", 99: "Thunder and hail",
}

DAILY = ("weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
         "precipitation_probability_max", "wind_speed_10m_max", "sunrise", "sunset")
HOURLY = ("temperature_2m", "weather_code", "precipitation_probability")


def forecast(client: Client, cfg: dict[str, Any], tz: str, now: dt.datetime) -> dict[str, Any]:
    """Fetch and condense the forecast for the configured place."""
    days = int(cfg.get("days", 2))
    data = client.json(API, params={
        "latitude": cfg["latitude"], "longitude": cfg["longitude"], "timezone": tz,
        "daily": ",".join(DAILY), "hourly": ",".join(HOURLY),
        "forecast_days": days + 1, "wind_speed_unit": "ms",
    })
    return condense(data, cfg, now.astimezone(ZoneInfo(tz)))


def condense(data: dict[str, Any], cfg: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    """Open-Meteo's columns → today, a few hours still ahead today, and the next days."""
    daily, hourly = data["daily"], data.get("hourly") or {}
    rows = [{k: (daily.get(k) or [None] * len(daily["time"]))[i] for k in ("time", *DAILY)}
            for i in range(len(daily["time"]))]
    today = next((r for r in rows if r["time"] == now.date().isoformat()), None)
    if today is None or today["temperature_2m_max"] is None:
        raise ValueError(f"no forecast for {now.date()}")

    hours = []
    chances = hourly.get("precipitation_probability") or []
    wanted = {int(h) for h in cfg.get("hours", [9, 12, 15, 18])}
    for i, t in enumerate(hourly.get("time", [])):
        at = dt.datetime.fromisoformat(t)
        if at.date() == now.date() and at.hour in wanted and at.hour > now.hour:
            temp = hourly["temperature_2m"][i]
            if temp is not None:
                code = hourly["weather_code"][i]
                hours.append({"time": f"{at:%H:%M}", "temp": _deg(temp), "code": code, "condition": _condition(code),
                              "precip_chance": chances[i] if i < len(chances) else None})

    return {
        "place": cfg["place"],
        "today": {**_day(today), "precip_mm": round(today["precipitation_sum"] or 0, 1),
                  "wind_ms": round(today["wind_speed_10m_max"] or 0),
                  "sunrise": (today["sunrise"] or "")[11:16], "sunset": (today["sunset"] or "")[11:16]},
        "hours": hours,
        "days": [_day(r) for r in rows if r["time"] > today["time"] and r["temperature_2m_max"] is not None]
                [:int(cfg.get("days", 2))],
    }


def _day(r: dict[str, Any]) -> dict[str, Any]:
    return {"date": r["time"], "high": _deg(r["temperature_2m_max"]), "low": _deg(r["temperature_2m_min"]),
            "code": r["weather_code"], "condition": _condition(r["weather_code"]),
            "precip_chance": r["precipitation_probability_max"]}


def _deg(t: float | None) -> int | None:
    return None if t is None else round(t)


def _condition(code: int | None) -> str:
    return CONDITIONS.get(code, "") if code is not None else ""
