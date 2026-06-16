"""Tests for the example weather_advice runbook + the generic (non-code-review)
dry-run preview it exercises."""

from typer.testing import CliRunner

from junior.cli import app
from junior.config import Settings
from junior.runbooks.weather import render, weather_api
from junior.runbooks.weather.runbook import (
    HourForecast,
    OutfitItem,
    WeatherAdvice,
    WeatherAdviceOutput,
    WeatherContext,
)

runner = CliRunner()


# --- A fake open-meteo + ip-api responder ---


def _fake_get(url: str, timeout: float = 10.0) -> dict:
    if "ip-api" in url:
        return {"status": "success", "city": "Testville", "country": "Nowhere",
                "lat": 10.0, "lon": 20.0}
    return {  # open-meteo forecast
        "timezone": "UTC",
        "current": {"time": "2026-07-01T12:00", "temperature_2m": 25.0,
                    "apparent_temperature": 26.0, "weather_code": 0, "wind_speed_10m": 5.0},
        "hourly": {
            "time": ["2026-07-01T12:00", "2026-07-01T13:00"],
            "temperature_2m": [25.0, 26.0],
            "apparent_temperature": [26.0, 27.0],
            "precipitation": [0.0, 0.5],
            "precipitation_probability": [0, 40],
            "weather_code": [0, 61],
            "wind_speed_10m": [5.0, 7.0],
        },
    }


# --- registration ---


def test_weather_runbook_registered():
    from junior.runbook.registry import available_runbooks, get_runbook

    assert "weather_advice" in available_runbooks()
    assert isinstance(get_runbook("weather_advice"), WeatherAdvice)


# --- season logic ---


def test_season_depends_on_hemisphere():
    assert weather_api._season(7, 45.0) == "summer"   # July, northern
    assert weather_api._season(7, -33.0) == "winter"  # July, southern
    assert weather_api._season(1, 52.0) == "winter"   # January, northern


# --- collect ---


def test_collect_weather_parses_forecast(monkeypatch):
    monkeypatch.setattr(weather_api, "_get_json", _fake_get)
    ctx = weather_api.collect_weather(Settings())
    assert ctx.location == "Testville, Nowhere"
    assert ctx.season == "summer"
    assert ctx.current_description == "clear sky"
    assert len(ctx.hourly) == 2
    assert ctx.hourly[0].time == "12:00"
    assert ctx.hourly[1].description == "light rain"  # weather_code 61


def test_collect_weather_location_override_skips_geolocation(monkeypatch):
    """`--context lat=..,lon=..` avoids both IP geolocation and geocoding calls."""
    def only_forecast(url: str, timeout: float = 10.0) -> dict:
        assert "ip-api" not in url and "geocoding" not in url
        return _fake_get(url)
    monkeypatch.setattr(weather_api, "_get_json", only_forecast)

    settings = Settings(context={"context": {"lat": "60.0", "lon": "30.0", "location": "Polargrad"}})
    ctx = weather_api.collect_weather(settings)
    assert ctx.location == "Polargrad"
    assert (ctx.latitude, ctx.longitude) == (60.0, 30.0)


# --- render: user message + additive --context ---


def test_build_user_message_includes_forecast_and_extra_context():
    ctx = WeatherContext(
        location="Testville", latitude=10.0, longitude=20.0, season="summer",
        local_time="2026-07-01 12:00", current_temp_c=25.0, current_description="clear sky",
        hourly=[HourForecast(time="12:00", temp_c=25.0, description="clear sky")],
    )
    msg = render.build_user_message(ctx, {"event": "outdoor wedding", "lat": "10", "lon": "20"})
    assert "Location: Testville" in msg
    assert "Season: summer" in msg
    assert "12:00" in msg
    # --context KEY=VAL is folded in as a hint (additive to the runbook context)…
    assert "event: outdoor wedding" in msg
    # …but the location-override keys are not echoed as hints
    hint_block = msg.split("Additional context")[1]
    assert "lat:" not in hint_block and "lon:" not in hint_block


def test_build_user_message_shows_zero_precip_probability():
    """precipitation_prob=0 (a real reading) must render, unlike None (no data)."""
    ctx = WeatherContext(
        location="Testville", latitude=10.0, longitude=20.0, season="summer",
        local_time="2026-07-01 12:00", current_temp_c=25.0, current_description="clear sky",
        hourly=[
            HourForecast(time="12:00", temp_c=25.0, description="clear sky", precipitation_prob=0),
            HourForecast(time="13:00", temp_c=26.0, description="clear sky", precipitation_prob=None),
        ],
    )
    msg = render.build_user_message(ctx, {})
    lines = [line for line in msg.splitlines() if line.strip().startswith(("12:00", "13:00"))]
    assert "0% precip" in lines[0]       # real 0 reading is shown
    assert "precip" not in lines[1]      # None stays hidden


def test_output_destination_reflects_publish_mode():
    """--publish = pretty terminal panel; default = -o file or stdout."""
    assert WeatherAdvice().output_destination(Settings(), publish_enabled=True) == "terminal"
    assert WeatherAdvice().output_destination(Settings(), publish_enabled=False) == "stdout"
    s = Settings(output={"output_file": "out.json"})
    assert WeatherAdvice().output_destination(s, publish_enabled=False) == "out.json"


def test_publish_renders_rich_panel(capsys):
    """--publish runs the custom publish — the Rich panel."""
    from junior.runbook.base import Usage

    out = WeatherAdviceOutput(
        summary="Mild.", outfit=[OutfitItem(item="jacket", reason="wind")], risks=["gusts"],
    )
    WeatherAdvice().publish(Settings(), out, Usage(), errors=[])
    assert "What to wear" in capsys.readouterr().out   # Rich panel title


def test_render_output_is_raw_json():
    """No --publish → framework emits render_output(): the raw result as JSON."""
    import json

    out = WeatherAdviceOutput(summary="Mild.", outfit=[OutfitItem(item="jacket", reason="wind")])
    data = json.loads(WeatherAdvice().render_output(out))
    assert data["summary"] == "Mild."
    assert data["outfit"][0]["item"] == "jacket"


def test_print_advice_renders_without_error():
    out = WeatherAdviceOutput(
        summary="Warm and clear.",
        outfit=[OutfitItem(item="T-shirt", reason="warm")],
        risks=["UV exposure"],
        tips=["bring water"],
    )
    render.print_advice(out, errors=["partial note"])  # must not raise


# --- dry-run preview works for a non-code-review context ---


def test_dry_run_generic_runbook(monkeypatch):
    fake = WeatherContext(
        location="Testville", latitude=10.0, longitude=20.0, season="summer",
        local_time="2026-07-01 12:00", current_temp_c=25.0, current_description="clear sky",
        hourly=[HourForecast(time="12:00", temp_c=25.0, description="clear sky")],
    )
    monkeypatch.setattr(weather_api, "collect_weather", lambda s: fake)

    result = runner.invoke(
        app, ["dry-run", "--runbook", "weather_advice", "--harness", "claudecode"]
    )
    assert result.exit_code == 0, result.stdout
    # plan + generic context dump (no changed-files table needed)
    assert "weather_advice" in result.stdout
    assert "Testville" in result.stdout
    assert "WeatherAdviceOutput" in result.stdout  # output schema in the plan
