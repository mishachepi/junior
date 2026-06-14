"""weather_advice — an example non-code-review runbook.

Shows the framework working far outside its origin domain: it collects live
weather + your location (no git, no LLM tools), asks the harness what to wear for
the next few hours, and "publishes" a structured Rich panel to the terminal.

Use it as a template for your own runbook: swap `collect` (any data source),
the two schemas, the prompt, and `publish` (any sink).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from junior.config import Settings
from junior.runbook.base import Runbook, Usage
from junior.runbook.registry import register_runbook


# --- context schema (what `collect` produces / the LLM sees) ---


class HourForecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: str
    temp_c: float
    feels_like_c: float | None = None
    precipitation_mm: float = 0.0
    precipitation_prob: int | None = None
    wind_kmh: float = 0.0
    description: str = ""


class WeatherContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    location: str
    latitude: float
    longitude: float
    timezone: str = ""
    local_time: str = ""
    season: str = ""
    current_temp_c: float = 0.0
    current_feels_like_c: float | None = None
    current_description: str = ""
    hourly: list[HourForecast] = Field(default_factory=list)


# --- result schema (what the LLM returns) ---


class OutfitItem(BaseModel):
    item: str
    reason: str


class WeatherAdviceOutput(BaseModel):
    summary: str
    outfit: list[OutfitItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


_BASE_PROMPT = """You are a concise, practical clothing advisor.

Given a person's location, the local season, the current weather, and the
hour-by-hour forecast for the next several hours, recommend what to wear so they
stay comfortable across that whole window — not just right now.

- Account for how conditions change over the window (warming, cooling, rain
  arriving, wind picking up). Dress for the range, layer when it shifts.
- `outfit`: concrete items with a one-line reason each (e.g. "light rain jacket
  — showers expected after 18:00").
- `risks`: things to watch out for (sudden rain, UV, cold snap, strong wind,
  ice). Empty if none.
- `tips`: optional extras (take an umbrella, sunscreen, swap shoes later).
Be specific and brief. Don't invent conditions not in the data."""


@register_runbook
class WeatherAdvice(Runbook[WeatherContext, WeatherAdviceOutput]):
    name = "weather_advice"
    description = "fetch local weather → advise what to wear (terminal only)"
    context_model = WeatherContext
    result_model = WeatherAdviceOutput

    # --- phase 1: collect (live weather, no git) ---
    def collect(self, settings: Settings) -> WeatherContext:
        from junior.runbooks.weather.weather_api import collect_weather

        return collect_weather(settings)

    # --- phase 2 inputs ---
    def render(self, context: WeatherContext, settings: Settings, *, file_access: bool) -> str:
        from junior.runbooks.weather.render import build_user_message

        # `file_access` is irrelevant here (no files to read); the data is always
        # inlined. `settings.context.context` (--context KEY=VAL) is folded in as
        # extra hints, demonstrating that CLI context augments the runbook's own.
        return build_user_message(context, dict(settings.context.context))

    def system_prompt(self, settings: Settings) -> str:
        from junior.prompt_loader import load_prompts

        # User `--prompt` / `context.prompts` entries are appended to the
        # runbook's base instructions — additive, exactly like code_review.
        extra = [p.body for p in load_prompts(list(settings.context.prompts)) if p.body.strip()]
        return "\n\n".join([_BASE_PROMPT, *extra])

    # --- phase 3: publish (terminal only) ---
    def publish(
        self,
        settings: Settings,
        result: WeatherAdviceOutput,
        usage: Usage,
        *,
        errors: list[str],
    ) -> None:
        # No platform — `--publish` renders the pretty Rich panel. Without it the
        # framework emits the raw result JSON (render_output) to stdout/-o.
        from junior.runbooks.weather.render import print_advice

        print_advice(result, errors=errors)

    # --- hooks ---
    def output_destination(self, settings: Settings, *, publish_enabled: bool) -> str:
        if publish_enabled:
            return "terminal"
        return settings.output.output_file or "stdout"

    def is_empty(self, context: WeatherContext) -> bool:
        return not context.hourly

    def summary(self, result: WeatherAdviceOutput) -> dict:
        return {"outfit_items": len(result.outfit), "risks": len(result.risks) or None}
