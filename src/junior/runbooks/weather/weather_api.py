"""Live weather + location collection for the weather_advice runbook.

Uses only the standard library (urllib) and two key-free public APIs, so the
example works on a core install with no extra deps:

- location: ip-api.com (IP geolocation) — override with `--context lat=..,lon=..`
  or `--context location="City, Country"`.
- forecast: open-meteo.com (no key).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import structlog

from junior.config import Settings
from junior.runbooks.weather.runbook import HourForecast, WeatherContext

logger = structlog.get_logger()

_FORECAST_HOURS = 10

# WMO weather-interpretation codes → short text (open-meteo `weather_code`).
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    56: "freezing drizzle", 57: "dense freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


def _get_json(url: str, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "junior-weather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted hosts)
        return json.loads(resp.read().decode("utf-8"))


def _resolve_location(overrides: dict[str, str]) -> tuple[float, float, str]:
    """(lat, lon, label) from --context overrides, geocoding, or IP geolocation."""
    if "lat" in overrides and "lon" in overrides:
        lat, lon = float(overrides["lat"]), float(overrides["lon"])
        return lat, lon, overrides.get("location", f"{lat:.3f}, {lon:.3f}")

    if "location" in overrides:  # geocode a place name via open-meteo
        q = urllib.parse.quote(overrides["location"])
        geo = _get_json(
            f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1"
        )
        hits = geo.get("results") or []
        if not hits:
            raise RuntimeError(f"could not geocode location '{overrides['location']}'")
        h = hits[0]
        label = ", ".join(p for p in (h.get("name"), h.get("country")) if p)
        return h["latitude"], h["longitude"], label

    ip = _get_json("http://ip-api.com/json/?fields=status,country,regionName,city,lat,lon")
    if ip.get("status") != "success":
        raise RuntimeError("IP geolocation failed — pass --context location=\"City\"")
    label = ", ".join(p for p in (ip.get("city"), ip.get("country")) if p)
    return ip["lat"], ip["lon"], label


def _season(month: int, latitude: float) -> str:
    north = [
        "winter", "winter", "spring", "spring", "spring", "summer",
        "summer", "summer", "autumn", "autumn", "autumn", "winter",
    ][month - 1]
    if latitude >= 0:
        return north
    return {"winter": "summer", "summer": "winter",
            "spring": "autumn", "autumn": "spring"}[north]


def collect_weather(settings: Settings) -> WeatherContext:
    """Geolocate, fetch the next-hours forecast, and assemble a WeatherContext."""
    lat, lon, label = _resolve_location(dict(settings.context.context))
    logger.debug("resolved location", location=label, lat=lat, lon=lon)

    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "hourly": (
            "temperature_2m,apparent_temperature,precipitation,"
            "precipitation_probability,weather_code,wind_speed_10m"
        ),
        "forecast_hours": _FORECAST_HOURS,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    })
    data = _get_json(f"https://api.open-meteo.com/v1/forecast?{params}")

    cur = data.get("current", {})
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])[:_FORECAST_HOURS]

    forecast: list[HourForecast] = []
    for i, t in enumerate(times):
        code = _at(hourly, "weather_code", i)
        forecast.append(HourForecast(
            time=t[11:16] if len(t) >= 16 else t,  # "YYYY-MM-DDTHH:MM" → "HH:MM"
            temp_c=_at(hourly, "temperature_2m", i) or 0.0,
            feels_like_c=_at(hourly, "apparent_temperature", i),
            precipitation_mm=_at(hourly, "precipitation", i) or 0.0,
            precipitation_prob=_int(_at(hourly, "precipitation_probability", i)),
            wind_kmh=_at(hourly, "wind_speed_10m", i) or 0.0,
            description=_WMO.get(code, "—"),
        ))

    cur_time = cur.get("time", "")
    month = int(cur_time[5:7]) if len(cur_time) >= 7 else 1
    return WeatherContext(
        location=label,
        latitude=lat,
        longitude=lon,
        timezone=data.get("timezone", ""),
        local_time=cur_time.replace("T", " "),
        season=_season(month, lat),
        current_temp_c=cur.get("temperature_2m", 0.0),
        current_feels_like_c=cur.get("apparent_temperature"),
        current_description=_WMO.get(cur.get("weather_code"), "—"),
        hourly=forecast,
    )


def _at(block: dict, key: str, i: int):
    seq = block.get(key) or []
    return seq[i] if i < len(seq) else None


def _int(value) -> int | None:
    return int(value) if value is not None else None
