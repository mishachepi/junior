"""User-message builder + Rich terminal publisher for weather_advice."""

from __future__ import annotations

from junior.runbooks.weather.runbook import WeatherAdviceOutput, WeatherContext


def build_user_message(context: WeatherContext, extra_context: dict[str, str]) -> str:
    """The exact text the harness sees: location, season, now, and the forecast."""
    lines = [
        f"Location: {context.location}  ({context.latitude:.3f}, {context.longitude:.3f})",
        f"Local time: {context.local_time}  ·  timezone: {context.timezone}",
        f"Season: {context.season}",
        "",
        f"Now: {context.current_temp_c:.0f}°C "
        + (f"(feels {context.current_feels_like_c:.0f}°C) " if context.current_feels_like_c is not None else "")
        + f"— {context.current_description}",
        "",
        f"Next {len(context.hourly)} hours:",
    ]
    for h in context.hourly:
        feels = f" (feels {h.feels_like_c:.0f}°)" if h.feels_like_c is not None else ""
        prob = f", {h.precipitation_prob}% precip" if h.precipitation_prob is not None else ""
        rain = f", {h.precipitation_mm:.1f}mm" if h.precipitation_mm else ""
        lines.append(
            f"  {h.time}  {h.temp_c:>4.0f}°C{feels}  {h.description}"
            f"  wind {h.wind_kmh:.0f} km/h{prob}{rain}"
        )

    # CLI `--context KEY=VAL` entries (minus location overrides) become extra hints.
    hints = {k: v for k, v in extra_context.items() if k not in ("lat", "lon", "location")}
    if hints:
        lines += ["", "Additional context from the user:"]
        lines += [f"  {k}: {v}" for k, v in hints.items()]

    lines += ["", "Advise what to wear across this window, plus any risks."]
    return "\n".join(lines)


def print_advice(result: WeatherAdviceOutput, *, errors: list[str]) -> None:
    """Render the LLM's advice as a structured Rich panel on stdout."""
    from rich.panel import Panel
    from rich.table import Table

    from junior.cli.console import console

    console.print(Panel(result.summary, title="🧥 What to wear", border_style="cyan"))

    if result.outfit:
        outfit = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        outfit.add_column("item", style="bold")
        outfit.add_column("why", style="dim", overflow="fold")
        for item in result.outfit:
            outfit.add_row(item.item, item.reason)
        console.print(outfit)

    if result.risks:
        console.print("\n[bold yellow]⚠ Risks[/]")
        for r in result.risks:
            console.print(f"  • {r}")

    if result.tips:
        console.print("\n[bold green]💡 Tips[/]")
        for t in result.tips:
            console.print(f"  • {t}")

    for e in errors:
        console.print(f"[dim]note: {e}[/]")
