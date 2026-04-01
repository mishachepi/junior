"""CLI entry point for Junior code review."""

import argparse
import logging
import sys
from pathlib import Path

import structlog
from pydantic import ValidationError

from junior import __version__
from junior.config import Settings
from junior.models import ReviewResult
from junior.prompt_loader import discover_prompts


def _available_prompt_names() -> list[str]:
    """Return sorted list of built-in prompt names."""
    return sorted(discover_prompts().keys())


def _parse_kv_args(raw: list[str], flag_name: str) -> dict[str, str]:
    """Parse a list of KEY=VALUE strings into a dict. Exits on bad format."""
    result = {}
    for arg in raw:
        if "=" not in arg:
            print(
                f"error: invalid {flag_name} format '{arg}', expected KEY=VALUE",
                file=sys.stderr,
            )
            sys.exit(2)
        key, _, value = arg.partition("=")
        result[key.strip()] = value.strip()
    return result


def _print_example_config() -> None:
    """Generate example .env config from Settings model."""
    from junior.config import AgentBackend

    print("# Junior — Environment Configuration")
    print("# Generate with: junior --config")
    print()

    fields = Settings.model_fields
    sections = {
        "AI Provider": ["model_provider", "model_name", "openai_api_key", "anthropic_api_key"],
        "Platform Tokens": ["gitlab_token", "github_token"],
        "Backend": ["agent_backend"],
        "Review": ["prompts", "prompts_dir", "fail_on_critical", "max_file_size", "max_concurrent_agents", "log_level"],
        "Output": ["publish_output"],
        "GitLab CI": [
            "ci_project_dir", "ci_project_id", "ci_merge_request_iid",
            "ci_merge_request_title", "ci_merge_request_description",
            "ci_merge_request_source_branch_name", "ci_merge_request_target_branch_name",
            "ci_merge_request_diff_base_sha", "ci_commit_sha", "ci_server_url",
        ],
        "GitHub Actions": ["github_repository", "github_event_number"],
    }

    for section, keys in sections.items():
        print(f"# --- {section} ---")
        for key in keys:
            if key not in fields:
                continue
            field = fields[key]
            default = field.default
            env_name = key.upper()
            if default is None or default == "" or default == {}:
                print(f"# {env_name}=")
            elif isinstance(default, bool):
                print(f"# {env_name}={str(default).lower()}")
            elif isinstance(default, AgentBackend):
                print(f"{env_name}={default.name.lower()}")
            elif isinstance(default, dict):
                continue
            else:
                print(f"# {env_name}={default}")
        print()


def _parse_args() -> argparse.Namespace:
    prompt_names = ", ".join(_available_prompt_names())

    parser = argparse.ArgumentParser(
        prog="junior",
        description="Junior — AI code review agent",
        epilog=(
            "Quick start:\n"
            "  junior --config > .env          # generate config, then edit .env\n"
            "\n"
            "Examples:\n"
            '  junior --context lang="Python 3.12 project" --prompts security,logic\n'
            "  junior --prompt-file ./my_rules.md --publish\n"
            "  junior --config my_project.env   # use custom config file\n"
            "\n"
            "Configuration is loaded from: env vars > .env > --config file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--backend",
        help="Agent backend: pydantic, claudecode, codex, deepagents (env: AGENT_BACKEND)",
    )
    parser.add_argument(
        "--model",
        help="Model name, e.g. claude-sonnet-4-6, gpt-5.4-mini (env: MODEL_NAME)",
    )
    parser.add_argument(
        "--project-dir",
        help="Path to git repository (env: CI_PROJECT_DIR, default: '.')",
    )
    parser.add_argument(
        "--target-branch",
        help="Target branch for diff (env: CI_MERGE_REQUEST_TARGET_BRANCH_NAME, default: main)",
    )
    parser.add_argument(
        "--prompts",
        help=f"Prompt names, comma-separated. Built-in: {prompt_names}. PROMPTS_DIR adds more (default: security,logic,design)",
    )
    parser.add_argument(
        "--prompt-file",
        action="append",
        default=[],
        metavar="FILE",
        help="Extra prompt .md file to include. Repeatable.",
    )
    parser.add_argument(
        "--context",
        action="append",
        default=[],
        metavar='KEY="text"',
        help='Extra prompt instructions for AI. Repeatable.',
    )
    parser.add_argument(
        "--context-file",
        action="append",
        default=[],
        metavar="KEY=path",
        help="Data files to add to context. Repeatable.",
    )
    parser.add_argument(
        "--config",
        nargs="?",
        const="__show__",
        default=None,
        metavar="FILE",
        help="Path to .env config file. Without argument: print example config and exit.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also post review to GitLab/GitHub (auto-detect from tokens)",
    )
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Skip AI review phase (collect only)",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        help="Write review to file instead of stdout",
    )
    return parser.parse_args()


def main() -> None:
    """Run code review pipeline: collect -> review -> publish.

    Exit codes: 0=success, 1=blocking issues, 2=config error, 3=runtime error
    """
    args = _parse_args()

    if args.config == "__show__":
        _print_example_config()
        return

    cli_kwargs: dict = {}
    if args.config:
        cli_kwargs["_env_file"] = args.config
    if args.backend:
        cli_kwargs["agent_backend"] = args.backend
    if args.model:
        cli_kwargs["model_name"] = args.model
    if args.project_dir:
        cli_kwargs["ci_project_dir"] = args.project_dir
    if args.target_branch:
        cli_kwargs["ci_merge_request_target_branch_name"] = args.target_branch
    if args.output_file:
        cli_kwargs["publish_output"] = args.output_file
    if args.context:
        cli_kwargs["context"] = _parse_kv_args(args.context, "--context")
    if args.context_file:
        cli_kwargs["context_files"] = _parse_kv_args(args.context_file, "--context-file")

    try:
        settings = Settings(**cli_kwargs)
    except ValidationError as e:
        for err in e.errors():
            print(f"config error: {err['msg']}", file=sys.stderr)
        sys.exit(2)

    _setup_logging(settings.log_level)
    logger = structlog.get_logger()

    # Load prompts (only when review is enabled)
    prompts = []
    if not args.no_review:
        prompt_names = args.prompts or settings.prompts
        try:
            from junior.prompt_loader import load_prompts, load_prompt_files

            prompts = load_prompts(prompt_names.split(","), settings.prompts_dir)
            if args.prompt_file:
                prompts.extend(load_prompt_files(args.prompt_file))
        except ValueError as e:
            logger.error("invalid prompts", error=str(e))
            sys.exit(2)

    config_errors = settings.preflight(
        review=not args.no_review,
        publish=args.publish,
    )
    if config_errors:
        for err in config_errors:
            logger.error("config error", error=err)
        sys.exit(2)

    logger.info(
        "pipeline starting",
        prompts=[p.name for p in prompts] if prompts else "(no-review)",
        agent_backend=settings.agent_backend.name.lower(),
        provider=settings.resolved_provider or "n/a",
        model=settings.resolved_model or "n/a",
        collector=settings.resolved_collector.name.lower(),
        publisher=settings.resolved_publisher.name.lower() if args.publish else "local",
        project_dir=settings.ci_project_dir,
        context_keys=list(settings.context.keys()) or None,
        context_file_keys=list(settings.context_files.keys()) or None,
    )

    # --- Phase 1: Collect ---
    from junior.collect import collect

    logger.info("phase 1: collecting context")
    try:
        context = collect(settings)
    except Exception as e:
        logger.error("collection failed", error=str(e))
        sys.exit(3)

    logger.info(
        "collection complete",
        diff_size=len(context.full_diff),
        changed_files=len(context.changed_files),
        extra_context_keys=list(context.extra_context.keys()) or None,
        mr_title=context.mr_title,
        commits=len(context.commit_messages),
    )

    if not context.full_diff:
        logger.info("no changes found, nothing to review")
        return

    # --- Phase 2: AI review ---
    result: ReviewResult | None = None

    if args.no_review:
        logger.info("phase 2: skipped (--no-review)")
    else:
        from junior.agent import review

        logger.info(
            "phase 2: AI review starting",
            backend=settings.agent_backend.name.lower(),
            prompts=len(prompts),
        )
        try:
            result = review(context, settings, prompts)
            logger.info(
                "review complete",
                findings=len(result.comments),
                recommendation=result.recommendation.value,
                tokens_used=result.tokens_used,
                critical=result.critical_count,
                high=result.high_count,
            )
        except Exception as e:
            logger.error("AI review failed", error=str(e))
            sys.exit(3)

    if result is None:
        result = ReviewResult(summary="", recommendation="comment")

    # --- Phase 3: Output ---
    from junior.publish.local import post_review as local_publish

    local_publish(settings, result)

    if args.publish:
        from junior.publish import publish

        platform = settings.resolved_publisher.name.lower()
        logger.info("publishing to platform", platform=platform)
        try:
            publish(settings, result)
            logger.info("published successfully", platform=platform)
        except Exception as e:
            logger.error("publish failed", platform=platform, error=str(e))
            sys.exit(3)

    if settings.fail_on_critical and result.has_blocking_issues:
        logger.warning(
            "blocking issues found, failing pipeline",
            critical=result.critical_count,
            recommendation=result.recommendation.value,
        )
        sys.exit(1)


def _setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with the given log level."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )
