from rich.console import Console
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner

console = Console()

VERDICT_STYLES = {
    "PASS": "bold green",
    "FAIL": "bold red",
    "UNCERTAIN": "bold yellow",
}


class StatusDisplay:
    def __init__(self):
        self._live = Live(console=console, transient=True)
        self._started = False

    def update(self, message: str):
        renderable = Spinner("dots", text=f"  {message}", style="cyan")
        if not self._started:
            self._live.start()
            self._started = True
        self._live.update(renderable)

    def pause(self):
        """Temporarily stop live display so we can print static content."""
        if self._started:
            self._live.stop()
            self._started = False

    def stop(self):
        self.pause()


def _format_vote_line(model_votes: dict) -> Text:
    """Format model votes as a colored inline summary."""
    t = Text()
    for i, (model, vote) in enumerate(model_votes.items()):
        if i > 0:
            t.append("  ")
        short = model.split("-")[0]  # claude, gpt, gemini, etc.
        style = {"PASS": "green", "FAIL": "red", "UNCERTAIN": "yellow"}.get(vote, "white")
        t.append(f"{short}:", style="dim")
        t.append(vote, style=style)
    return t


def format_result(result: dict) -> Text:
    verdict = result.get("verdict", "UNCERTAIN")
    confidence = result.get("confidence", 0.0)
    headline = result.get("headline") or result.get("summary", "")
    strengths = result.get("strengths", [])
    issues = result.get("issues", [])
    fixes = result.get("fixes", [])
    unique_catches = result.get("unique_catches", [])
    model_votes = result.get("model_votes", {})
    consensus = result.get("consensus", "")
    dissent = result.get("dissent")
    elapsed = result.get("elapsed", 0.0)

    style = VERDICT_STYLES.get(verdict, "bold white")
    pct = f"{int(confidence * 100)}%"

    output = Text()

    # Headline
    output.append(f"{verdict}  ", style=style)
    output.append(f"{pct}  ", style=style)
    output.append(headline)

    # Vote breakdown
    if model_votes:
        output.append("\n\n")
        output.append(_format_vote_line(model_votes))
        if consensus:
            output.append(f"  ({consensus})", style="dim")

    # Strengths
    if strengths:
        output.append("\n")
        for s in strengths:
            output.append(f"\n+ {s}", style="green")

    # Issues
    if issues:
        output.append("\n")
        for issue in issues:
            output.append(f"\n- {issue}", style="red")

    # Unique catches — what each model uniquely spotted
    if unique_catches:
        output.append("\n")
        for catch in unique_catches:
            output.append(f"\n! {catch}", style="magenta")

    # Fixes
    if fixes:
        output.append("\n")
        for fix in fixes:
            output.append(f"\n\u2192 {fix}", style="cyan")

    # Dissent
    if dissent:
        output.append("\n\n")
        output.append("Dissent: ", style="bold yellow")
        output.append(dissent, style="yellow")

    # Footer
    usage = result.get("usage", {})
    footer_parts = [f"completed in {elapsed}s"]
    total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    if total_tokens:
        reasoning = usage.get("reasoning_tokens", 0)
        footer_parts.append(f"{total_tokens:,} tokens")
        if reasoning:
            footer_parts.append(f"{reasoning:,} reasoning")
    cost = result.get("cost", 0)
    if cost:
        footer_parts.append(f"~${cost:.2f}")
    output.append(f"\n\n{' \u2022 '.join(footer_parts)}", style="dim")

    return output


def format_transcript(transcript: list[dict]) -> Text:
    return _format_transcript_text(transcript)


_ROUND_LABELS = [
    "Initial Assessment",
    "Cross-Examination",
    "Rebuttal",
    "Final Rebuttal",
]


def _format_transcript_text(transcript: list[dict]) -> Text:
    rounds: dict[int, list[tuple[str, str, str | None]]] = {}
    for entry in transcript:
        r = entry["round"]
        rounds.setdefault(r, []).append((entry["model"], entry["response"], entry.get("role")))

    output = Text()
    for r in sorted(rounds):
        label = _ROUND_LABELS[r] if r < len(_ROUND_LABELS) else f"Round {r}"
        output.append(f"--- {label} ---\n", style="bold cyan")
        for model, response, role in rounds[r]:
            role_tag = f" ({role})" if role else ""
            output.append(f"[{model}{role_tag}]\n", style="bold")
            output.append(f"{response}\n\n")
    return output


def print_round(round_num: int, entries: list[dict]):
    """Print a single round's results live as they come in."""
    label = _ROUND_LABELS[round_num] if round_num < len(_ROUND_LABELS) else f"Round {round_num}"
    console.print(f"\n--- {label} ---", style="bold cyan")
    for entry in entries:
        role = entry.get("role")
        role_tag = f" ({role})" if role else ""
        console.print(f"[{entry['model']}{role_tag}]", style="bold")
        console.print(entry["response"])
        console.print()


def print_result(result: dict):
    text = format_result(result)
    console.print(text)
