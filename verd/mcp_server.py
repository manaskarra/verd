import asyncio
import json
import os
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from verd.engine import run_debate


def _validate_env() -> None:
    """Validate required environment variables before starting the MCP server.

    Prints actionable error messages to stderr and exits if misconfigured,
    so users see a clear diagnosis instead of a cryptic API error mid-run.
    """
    errors = []

    py_major, py_minor = sys.version_info.major, sys.version_info.minor
    if (py_major, py_minor) < (3, 11):
        errors.append(
            f"  - Python >= 3.11 required, found {py_major}.{py_minor}.\n"
            f"    Run: python3.11 -m pip install verd"
        )

    if not os.getenv("OPENAI_API_KEY"):
        errors.append(
            "  - OPENAI_API_KEY is not set.\n"
            "    Add it to the 'env' block in your MCP config JSON, or export it in your shell."
        )

    if not os.getenv("OPENAI_BASE_URL"):
        errors.append(
            "  - OPENAI_BASE_URL is not set.\n"
            "    Set it to your provider's base URL, e.g.:\n"
            '      "OPENAI_BASE_URL": "https://openrouter.ai/api/v1"'
        )

    if errors:
        print(
            "verd-mcp: startup failed — fix the following before retrying:\n"
            + "\n".join(errors),
            file=sys.stderr,
        )
        sys.exit(1)

app = Server("verd")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="verd",
            description=(
                "Run a multi-LLM debate (4 models, 2 rounds). "
                "Use for standard verification of code, answers, or decisions. "
                "IMPORTANT: Only call once per user request — combine all claims into one call. "
                "Never split into multiple parallel verd calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim": {
                        "type": "string",
                        "description": (
                            "The question or claim to evaluate "
                            "e.g. 'is this implementation correct?'"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "The content to evaluate (code, text, thread). "
                            "Omit to debate the claim alone."
                        ),
                    },
                },
                "required": ["claim"],
            },
        ),
        Tool(
            name="verdl",
            description=(
                "Run a fast 2-model debate (light mode). "
                "Use for quick checks where speed matters. "
                "Only call once per user request — never split into multiple parallel calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["claim"],
            },
        ),
        Tool(
            name="verdh",
            description=(
                "Run a deep 5-model debate (heavy mode, up to 60s). "
                "Use for high-stakes code reviews, security checks, or critical decisions. "
                "Only call once per user request — combine all questions into one claim. "
                "Never split into multiple parallel calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["claim"],
            },
        ),
    ]


async def _send_progress(msg: str):
    """Send a log message to the MCP client as a progress update."""
    try:
        ctx = app.request_context
        await ctx.session.send_log_message("info", msg, logger="verd")
    except Exception:
        pass  # Not in a request context or client doesn't support logging


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    mode_map = {"verdl": "verdl", "verd": "verd", "verdh": "verdh"}
    mode = mode_map.get(name, "verd")
    claim = arguments["claim"]
    content = arguments.get("content", "")

    # Status callback that sends MCP log notifications
    async def status_callback(msg: str):
        await _send_progress(msg)

    result = await run_debate(
        content, claim, mode,
        status_callback=status_callback,
    )
    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
            raise_exceptions=True,
        )


def main():
    _validate_env()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
