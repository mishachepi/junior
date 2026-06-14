#!/usr/bin/env python3
"""collect phase — print a plain-text weather brief (becomes the AI user message).

Standard library only (urllib). Location resolution:
  - JUNIOR_CONTEXT_LOCATION  (set via `--context location="City"`) → geocoded, else
  - IP geolocation.
Both APIs are key-free (open-meteo + ip-api).
"""

import json
import os
import urllib.parse
import urllib.request


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "junior-weather-example/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def _resolve_location() -> tuple[float, float, str]:
    place = os.environ.get("JUNIOR_CONTEXT_LOCATION")
    if place:
        q = urllib.parse.quote(place)
        hit = _get(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1")
        results = hit.get("results") or []
        if not results:
            raise SystemExit(f"could not geocode location '{place}'")
        r = results[0]
        label = ", ".join(p for p in (r.get("name"), r.get("country")) if p)
        return r["latitude"], r["longitude"], label
    ip = _get("http://ip-api.com/json/?fields=status,city,country,lat,lon")
    if ip.get("status") != "success":
        raise SystemExit('IP geolocation failed — pass --context location="City"')
    label = ", ".join(p for p in (ip.get("city"), ip.get("country")) if p)
    return ip["lat"], ip["lon"], label


def main() -> None:
    lat, lon, label = _resolve_location()
    fc = _get(
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature"
        "&hourly=temperature_2m,precipitation_probability"
        "&forecast_hours=10&timezone=auto"
    )
    cur = fc.get("current", {})
    hourly = fc.get("hourly", {})

    print(f"Location: {label}")
    print(f"Now: {cur.get('temperature_2m')}°C (feels {cur.get('apparent_temperature')}°C)")
    print("Next hours:")
    times = hourly.get("time", [])[:10]
    temps = hourly.get("temperature_2m", [])
    pops = hourly.get("precipitation_probability", [])
    for i, t in enumerate(times):
        temp = temps[i] if i < len(temps) else "?"
        pop = pops[i] if i < len(pops) else "?"
        print(f"  {t[11:16]}  {temp}°C  rain {pop}%")
    print("\nAdvise what to wear across this window, plus any risks.")


if __name__ == "__main__":
    main()
