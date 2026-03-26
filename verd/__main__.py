import argparse
import asyncio
import json
import logging
import sys

from verd.config import VERSION, DEBATER_MAX_TOKENS, MODEL_PRICING
from verd.context import build_context
from verd.engine import run_debate
from verd.log import setup as setup_logging
from verd.models import MODELS
from verd.output import print_result, StatusDisplay
from verd.user_config import load_user_config, apply_config_to_args
from verd.version_check import check_version


def make_parser():
    parser = argparse.ArgumentParser(
        description="Multi-LLM debate for confident answers"
    )
    parser.add_argument("--version", action="version", version=f"verd {VERSION}")
    parser.add_argument("claim", help="The claim or question to evaluate")

    # Content input — pick one
    content = parser.add_argument_group("content input")
    content.add_argument("-c", "--context", help="Inline content string")
    content.add_argument(
        "-f", "--file", nargs="+", metavar="FILE",
        help="One or more files to evaluate",
    )
    content.add_argument(
        "-d", "--dir", nargs="?", const="", default=None, metavar="DIR",
        help="Read all files in a directory (default: current dir)",
    )
    content.add_argument(
        "-g", "--git", action="store_true",
        help="Use unstaged git diff as content",
    )
    content.add_argument(
        "-gs", "--git-staged", action="store_true",
        help="Use staged git diff as content",
    )
    content.add_argument(
        "-gb", "--git-branch", metavar="REF",
        help="Use git diff REF...HEAD as content (e.g. main)",
    )

    # Filters for -d
    filters = parser.add_argument_group("directory filters (use with -d)")
    filters.add_argument(
        "-a", "--all", action="store_true",
        help="Scan all files, skip smart selection (for full codebase reviews)",
    )
    filters.add_argument(
        "--ext", nargs="+", metavar="EXT",
        help="Filter by extension (e.g. --ext .py .ts)",
    )
    filters.add_argument(
        "--exclude", nargs="+", metavar="PATTERN",
        help="Glob patterns to exclude (e.g. --exclude 'test_*' '*.spec.*')",
    )

    # Model overrides
    overrides = parser.add_argument_group("model overrides")
    overrides.add_argument(
        "--judge", metavar="MODEL",
        help="Override judge model (e.g. --judge gpt-5.4)",
    )
    overrides.add_argument(
        "--debaters", metavar="MODEL", nargs="+",
        help="Override debater models (e.g. --debaters gpt-4.1 claude-sonnet-4-6)",
    )

    # Output & safety
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Hide debate transcript, show only verdict",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output raw JSON",
    )
    parser.add_argument(
        "--timeout", type=int, default=None,
        help="Override timeout per model call (seconds)",
    )
    parser.add_argument(
        "--budget", type=float, default=None, metavar="USD",
        help="Max cost in USD — aborts before running if estimated cost exceeds budget",
    )
    return parser


def _estimate_debate_cost(mode: str) -> float:
    """Rough upper-bound cost estimate for a debate run."""
    cfg = MODELS[mode]
    num_debaters = len(cfg["debaters"])
    rounds = cfg["rounds"]
    tokens_per_call = DEBATER_MAX_TOKENS[mode]
    # Estimate: each call uses ~2x debater tokens (prompt + completion)
    # rounds+1 because round 0 + N follow-ups, plus judge
    total_calls = num_debaters * (rounds + 1) + 1
    # Use average pricing as rough estimate
    avg_input = sum(p[0] for p in MODEL_PRICING.values()) / len(MODEL_PRICING)
    avg_output = sum(p[1] for p in MODEL_PRICING.values()) / len(MODEL_PRICING)
    est = total_calls * (tokens_per_call * avg_input + tokens_per_call * avg_output) / 1_000_000
    return round(est, 2)


def _apply_model_overrides(mode: str, args) -> None:
    """Apply --judge and --debaters overrides to the MODELS config in-place."""
    cfg = MODELS[mode]
    if args.judge:
        cfg["judge"] = args.judge
    if args.debaters:
        roles = list(MODELS[mode]["debaters"][i].get("role", "analyst")
                     for i in range(len(args.debaters)))
        # Pad roles if more debaters than original, cycle through defaults
        from verd.models import ROLES
        default_roles = list(ROLES.keys())
        while len(roles) < len(args.debaters):
            roles.append(default_roles[len(roles) % len(default_roles)])
        cfg["debaters"] = [
            {"model": m, "role": r}
            for m, r in zip(args.debaters, roles)
        ]


def run(mode: str):
    check_version()
    parser = make_parser()
    args = parser.parse_args()

    # Configure logging
    setup_logging(logging.DEBUG if getattr(args, 'verbose', False) else logging.WARNING)

    # Load user config (file + env vars), then let CLI flags override
    user_cfg = load_user_config(mode)
    apply_config_to_args(args, user_cfg)

    content, claim, files = build_context(args)

    if not content and not claim:
        parser.print_help()
        sys.exit(1)

    # Apply model overrides before anything else
    _apply_model_overrides(mode, args)

    # Cost guardrail
    if args.budget is not None:
        est = _estimate_debate_cost(mode)
        if est > args.budget:
            print(
                f"Estimated cost ~${est:.2f} exceeds budget ${args.budget:.2f}. "
                f"Use a lighter mode (verdl/verd) or increase --budget.",
                file=sys.stderr,
            )
            sys.exit(1)

    # --all flag: skip smart file selection, send everything
    if getattr(args, 'all', False) and files is not None:
        from verd.context import files_to_content, MAX_CONTENT_CHARS
        total_chars = sum(len(text) for _, text, _ in files)
        content = files_to_content(files)
        if total_chars > MAX_CONTENT_CHARS:
            skipped = total_chars - MAX_CONTENT_CHARS
            print(
                f"\n⚠  {len(files)} files totaling {total_chars // 1000}K chars — "
                f"truncated to {MAX_CONTENT_CHARS // 1000}K ({skipped // 1000}K chars lost).\n"
                f"   Some files were cut off. For better results, drop -a and let\n"
                f"   the smart selector pick relevant files, or narrow with --ext / -f.\n",
                file=sys.stderr,
            )
        else:
            print(f"scanning all {len(files)} files ({total_chars // 1000}K chars)", file=sys.stderr)
        files = None  # don't run selector

    status = StatusDisplay()
    try:
        result = asyncio.run(
            run_debate(
                content,
                claim,
                mode,
                timeout_override=args.timeout,
                status_display=status,
                files=files,
                verbose=not args.quiet,
            )
        )
    except RuntimeError as e:
        status.stop()
        print(f"\n  Error: {e}", file=sys.stderr)
        if "No models responded" in str(e) or "API" in str(e):
            print(
                "\n  Looks like verd isn't configured yet."
                "\n  Run: verd setup\n",
                file=sys.stderr,
            )
        sys.exit(1)
    finally:
        status.stop()

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_result(result)

    # Exit 0 for any completed verdict; exit 1 only for actual errors
    sys.exit(0)


def _cmd_setup():
    """Interactive setup wizard — generates .env or MCP config."""
    import shutil

    DIV = "-" * 50

    print(f"\n  verd {VERSION} — setup\n")
    print(DIV)

    py_major, py_minor = sys.version_info.major, sys.version_info.minor
    if (py_major, py_minor) < (3, 11):
        print(
            f"  WARNING: Python {py_major}.{py_minor} detected — verd requires Python 3.11+.\n"
            f"  Install a newer Python and reinstall: pip3.11 install verd",
            file=sys.stderr,
        )
        print(DIV)

    # Usage mode
    print("\n  How are you using verd?\n")
    print("    1) CLI     (terminal commands: verd, verdl, verdh)")
    print("    2) MCP     (inside Claude Code, Cursor, etc.)")
    mode = input("\n  Enter 1 or 2: ").strip()

    print(f"\n{DIV}")

    # Provider selection
    print("\n  Which provider?\n")
    print("    1) OpenRouter  (recommended — one key for all models)")
    print("    2) LiteLLM     (self-hosted proxy)")
    print("    3) Other       (any OpenAI-compatible API)")
    provider = input("\n  Enter 1, 2, or 3: ").strip()

    print(f"\n{DIV}")

    # Build env vars based on provider
    env = {}
    if provider == "1":
        env = {
            "OPENAI_API_KEY": "your-openrouter-key",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        }
    elif provider == "2":
        env = {
            "OPENAI_API_KEY": "your-litellm-key",
            "OPENAI_BASE_URL": "https://your-litellm-url",
            "VERDL_JUDGE": "o4-mini",
            "VERDL_DEBATERS": "gpt-4.1-mini,gemini-3.1-flash-lite-preview",
            "VERD_JUDGE": "o3",
            "VERD_DEBATERS": "claude-sonnet-4-6,gpt-4.1,gemini-3.1-pro-preview,gpt-4.1-mini",
            "VERDH_JUDGE": "o3",
            "VERDH_DEBATERS": "claude-opus-4-6,deepseek-r1,gemini-3.1-pro-preview,sonar-pro,gpt-4.1",
        }
        print("\n  Ensure the model names above match what your provider exposes.")
    else:
        env = {
            "OPENAI_API_KEY": "your-api-key",
            "OPENAI_BASE_URL": "https://your-api/v1",
            "VERDL_JUDGE": "o4-mini",
            "VERDL_DEBATERS": "gpt-4.1-mini,gemini-3.1-flash-lite-preview",
            "VERD_JUDGE": "o3",
            "VERD_DEBATERS": "claude-sonnet-4-6,gpt-4.1,gemini-3.1-pro-preview,gpt-4.1-mini",
            "VERDH_JUDGE": "o3",
            "VERDH_DEBATERS": "claude-opus-4-6,deepseek-r1,gemini-3.1-pro-preview,sonar-pro,gpt-4.1",
        }
        print("\n  Ensure the model names above match what your provider exposes.")

    print(f"\n{DIV}")

    if mode == "1":
        # CLI — print .env contents to copy
        print("\n  Add this to your .env file:\n")
        for k, v in env.items():
            print(f"    {k}={v}")
        print("\n  Replace the placeholders with your actual keys, then run:")
        print("    verd \"your question here\"")

    else:
        # MCP — print JSON config
        verd_mcp_path = shutil.which("verd-mcp")
        if not verd_mcp_path:
            print(
                "\n  WARNING: verd-mcp not found on PATH.\n"
                "  Try: export PATH=\"$(python3 -m site --user-base)/bin:$PATH\"\n"
                "  Then re-run: verd setup",
                file=sys.stderr,
            )
            verd_mcp_path = "<run 'which verd-mcp' to find the path>"

        config = {
            "mcpServers": {
                "verd": {
                    "command": verd_mcp_path,
                    "env": env,
                }
            }
        }

        print("\n  Add this to ~/.claude.json (Claude Code) or ~/.cursor/mcp.json (Cursor):\n")
        print(json.dumps(config, indent=2))
        print("\n  Replace the OPENAI_API_KEY placeholder with your actual key.")

    print(f"\n{DIV}")
    print(f"\n  Repo: https://github.com/manaskarra/verd\n")


def main_light():
    run("verdl")


def main_default():
    # Handle 'verd setup' as a special subcommand
    if len(sys.argv) == 2 and sys.argv[1] == "setup":
        _cmd_setup()
        return
    # Bare 'verd' with no args — show welcome + setup hint
    if len(sys.argv) == 1:
        print(
            f"\n  verd {VERSION} — multi-LLM debate engine\n"
            f"\n  Usage:  verd \"your question here\""
            f"\n  Setup:  verd setup\n",
        )
        sys.exit(0)
    run("verd")


def main_heavy():
    run("verdh")


if __name__ == "__main__":
    main_default()
