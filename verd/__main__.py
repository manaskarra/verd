import argparse
import asyncio
import json
import sys

from verd.config import VERSION
from verd.context import build_context
from verd.engine import run_debate
from verd.output import print_result, StatusDisplay


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

    # Output
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
    return parser


def run(mode: str):
    parser = make_parser()
    args = parser.parse_args()
    content, claim, files = build_context(args)

    if not content and not claim:
        parser.print_help()
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
    finally:
        status.stop()

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_result(result)

    # Exit codes only when piped or --json (useful for scripting: verd "check" && deploy)
    # Interactive use always exits 0 so it doesn't look like an error
    if args.json_output or not sys.stdout.isatty():
        verdict = result.get("verdict", "UNCERTAIN")
        exit_codes = {"PASS": 0, "FAIL": 1, "UNCERTAIN": 2}
        sys.exit(exit_codes.get(verdict, 2))


def main_light():
    run("verdl")


def main_default():
    run("verd")


def main_heavy():
    run("verdh")


if __name__ == "__main__":
    main_default()
