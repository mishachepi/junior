# Example: a manifest runbook (`weather-advice`)

A complete [repo-local runbook](../../../adding_runbooks.md#4-repo-local-in-juniorrunbooks)
defined **without any Python class** — just a YAML manifest plus two scripts. It fetches the
local weather and asks the harness what to wear.

```
weather/
  weather.yaml    # the manifest (schema + system_prompt + collect/publish)
  schema.json     # JSON-Schema for the AI's structured result
  prompt.md       # the system prompt / instructions
  collect.py      # phase 1 — prints the user message (the weather brief)
  publish.py      # phase 3 — receives the AI's JSON result on stdin
```

## How the pieces fit

| Manifest key | What Junior does with it |
|---|---|
| `schema` | Builds the harness's **output schema** from this JSON-Schema. |
| `system_prompt` | The task instructions (file or inline). Your `--prompt` text is appended. |
| `collect` | Runs the command; its **STDOUT becomes the user message** the AI sees. |
| `publish` | Runs **only with `--publish`**; the AI's **validated JSON is piped to its STDIN**. Without `--publish` you get that JSON on stdout/`-o` instead. |

Your scripts also get `JUNIOR_PROJECT_DIR` and one `JUNIOR_CONTEXT_<KEY>` per
`--context KEY=VAL` in the environment (here, `--context location="Tokyo"` →
`JUNIOR_CONTEXT_LOCATION`).

## Use it

```bash
# 1. Copy this folder into the repo you want it in:
mkdir -p .junior/runbooks
cp -r path/to/this/weather .junior/runbooks/weather

# 2. Opt in (it executes the scripts above, so it's off by default):
echo "local_runbooks: true" >> .junior.yaml

# 3. Run it
junior config list                                  # weather-advice now appears
junior dry-run --runbook weather-advice            # preview: runs collect, no AI call
junior run --runbook weather-advice                # raw result JSON → stdout
junior run --runbook weather-advice --publish      # full run → harness → publish.py
junior run --runbook weather-advice --publish --context location="Tokyo"
```

Requires `python3` and `curl`-free networking (the scripts use Python's stdlib `urllib`).
No API keys — the weather/geolocation APIs are public.

> [!NOTE]
> For the same runbook written as a **Python class** instead of a manifest, see the
> built-in `weather_advice` in `src/junior/runbooks/weather/`.
