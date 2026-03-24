"""Run verd against the Martian Code Review Benchmark (50 real PRs).

Uses the golden comments from github.com/withmartian/code-review-benchmark
as ground truth. For each PR:
  1. Fetch the PR diff from GitHub
  2. Run single-model baselines (claude-sonnet, gpt-5.4)
  3. Run verd (4-model debate) or verdh (5-model + web)
  4. Extract candidate issues from each response
  5. Judge candidates against golden comments (precision/recall)

Requires:
  - gh CLI authenticated (for fetching PR diffs)
  - OPENAI_API_KEY + OPENAI_BASE_URL in env (for verd + baselines)
  - Clone of withmartian/code-review-benchmark at BENCHMARK_REPO path

Usage:
  python benchmark/run_martian_benchmark.py [--mode verd|verdh] [--limit N] [--baselines]
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from verd.engine import run_debate
from verd.config import get_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BENCHMARK_REPO = os.environ.get(
    "MARTIAN_BENCHMARK_REPO",
    "/tmp/code-review-benchmark",
)
GOLDEN_DIR = Path(BENCHMARK_REPO) / "offline" / "golden_comments"
RESULTS_DIR = Path(__file__).parent / "results" / "martian"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

BASELINES = ["claude-opus-4-6", "gpt-5.4"]

MAX_DIFF_CHARS = 80_000  # ~20k tokens — fits in all model context windows

REVIEW_PROMPT = (
    "You are an expert code reviewer. Review the following pull request diff.\n\n"
    "List every bug, security issue, logic error, correctness problem, and "
    "significant concern you find.\n\n"
    "IMPORTANT RULES:\n"
    "- List each issue as a SEPARATE numbered item, even if issues are related\n"
    "- Be specific — cite the exact file, line, and code\n"
    "- Do NOT merge multiple issues into one bullet point\n"
    "- Do NOT include style nits, formatting suggestions, or documentation comments\n"
    "- Focus on correctness, security, logic, and behavior bugs\n\n"
    "For each issue, use this exact format:\n"
    "1. [file:line] Short description of the bug or issue. "
    "Explanation of why it's a problem and what could go wrong.\n\n"
    "PR Title: {title}\n\n"
    "Diff:\n```\n{diff}\n```"
)

EXTRACT_PROMPT = """You are extracting individual code review issues from a review.

Review text:
{review}

Extract each distinct code issue, bug, or concern as a separate item.
Ignore meta-commentary, greetings, or formatting.
If no actionable issues, return an empty list.

Respond with ONLY a JSON object:
{{"issues": ["issue 1", "issue 2", ...]}}"""

JUDGE_PROMPT = """Determine if the candidate issue matches the golden (expected) comment.

Golden Comment (the issue we're looking for):
{golden_comment}

Candidate Issue (from the review):
{candidate}

Do they identify the SAME underlying issue? Different wording is fine if it's the same problem.

Respond with ONLY a JSON object:
{{"match": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""


# ---------------------------------------------------------------------------
# Smart diff truncation
# ---------------------------------------------------------------------------

def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    """Truncate a diff smartly — keep code changes, drop boilerplate.

    Strategy:
    1. Parse into per-file hunks
    2. Deprioritize: lock files, generated files, tests, snapshots, migrations
    3. Keep highest-priority hunks until budget is exhausted
    4. If a single file still overflows, truncate it with a marker
    """
    if len(diff) <= max_chars:
        return diff

    # Split diff into per-file sections
    files = []
    current = []
    current_name = None
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            if current_name:
                files.append((current_name, "\n".join(current)))
            current = [line]
            # Extract filename from "diff --git a/path b/path"
            parts = line.split(" b/")
            current_name = parts[-1] if len(parts) > 1 else line
        else:
            current.append(line)
    if current_name:
        files.append((current_name, "\n".join(current)))

    if not files:
        return diff[:max_chars] + "\n[truncated]"

    # Score files: lower = less important (drop first)
    LOW_PRI_PATTERNS = (
        "lock", "generated", "snapshot", "__snapshots__", ".snap",
        "migration", "vendor/", "dist/", "build/", ".min.", ".map",
        "package-lock", "yarn.lock", "pnpm-lock", "go.sum", "Gemfile.lock",
        "CHANGELOG", "LICENSE",
    )
    TEST_PATTERNS = ("test", "spec", "_test.", ".test.", "fixture")

    def file_priority(name: str) -> int:
        lower = name.lower()
        if any(p in lower for p in LOW_PRI_PATTERNS):
            return 0
        if any(p in lower for p in TEST_PATTERNS):
            return 1
        return 2

    # Sort: high priority first, then by size (smaller first to fit more files)
    scored = [(file_priority(name), len(content), name, content) for name, content in files]
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Pack hunks into budget
    result = []
    remaining = max_chars
    included = 0
    for _pri, size, name, content in scored:
        if remaining <= 0:
            break
        if size <= remaining:
            result.append(content)
            remaining -= size
            included += 1
        else:
            # Partial: truncate this file's content
            result.append(content[:remaining] + f"\n[... {name} truncated, {size - remaining} chars omitted]")
            remaining = 0
            included += 1

    dropped = len(scored) - included
    out = "\n".join(result)
    if dropped > 0:
        out += f"\n\n[{dropped} low-priority file(s) omitted to fit context window]"
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_golden_comments() -> list[dict]:
    """Load all 50 PRs with golden comments."""
    prs = []
    for json_file in sorted(GOLDEN_DIR.glob("*.json")):
        with open(json_file) as f:
            entries = json.load(f)
        for entry in entries:
            entry["_source_file"] = json_file.stem
            prs.append(entry)
    return prs


def _github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _curl_github(api_url: str, accept: str = "application/vnd.github.v3+json") -> str | None:
    """Fetch from GitHub API using curl (avoids Python SSL issues)."""
    import subprocess
    cmd = ["curl", "-s", "-H", f"Accept: {accept}"]
    token = _github_token()
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd.append(api_url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def fetch_pr_diff(pr_url: str) -> str | None:
    """Fetch PR diff from GitHub API."""
    m = re.match(r"https://github.com/([^/]+/[^/]+)/pull/(\d+)", pr_url)
    if not m:
        return None
    repo, pr_num = m.group(1), m.group(2)
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}"
    return _curl_github(api_url, accept="application/vnd.github.v3.diff")


def fetch_changed_files(pr_url: str) -> list[str] | None:
    """Fetch list of changed filenames from GitHub API."""
    m = re.match(r"https://github.com/([^/]+/[^/]+)/pull/(\d+)", pr_url)
    if not m:
        return None
    repo, pr_num = m.group(1), m.group(2)
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/files"
    raw = _curl_github(api_url)
    if not raw:
        return None
    try:
        files = json.loads(raw)
        return [f["filename"] for f in files[:15]]
    except (json.JSONDecodeError, KeyError):
        return None


async def call_llm(model: str, prompt: str, max_tokens: int = 4096) -> str:
    """Call a single model and return the response text."""
    response = await asyncio.wait_for(
        get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=max_tokens,
        ),
        timeout=120,
    )
    return response.choices[0].message.content or ""


async def extract_issues(review_text: str) -> list[str]:
    """Use LLM to extract individual issues from a review."""
    prompt = EXTRACT_PROMPT.format(review=review_text[:8000])
    try:
        text = await call_llm("gpt-5-mini", prompt, max_tokens=2048)
        # Strip markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        return data.get("issues", [])
    except Exception:
        # Fallback: split by numbered lines
        issues = re.findall(r'(?:^|\n)\s*\d+[.)]\s+(.+)', review_text)
        return issues


async def judge_match(golden_comment: str, candidate: str) -> dict:
    """Use LLM to judge if candidate matches golden comment."""
    prompt = JUDGE_PROMPT.format(
        golden_comment=golden_comment, candidate=candidate,
    )
    try:
        text = await call_llm("gpt-5-mini", prompt, max_tokens=512)
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        return {"match": False, "confidence": 0, "reasoning": f"Error: {e}"}


async def evaluate_candidates(
    golden_comments: list[dict], candidates: list[str],
) -> dict:
    """Evaluate candidates against golden comments. Returns precision/recall."""
    if not golden_comments:
        return {"skipped": True}
    if not candidates:
        return {
            "tp": 0, "fp": 0, "fn": len(golden_comments),
            "precision": 0.0, "recall": 0.0,
            "total_candidates": 0, "total_golden": len(golden_comments),
            "true_positives": [], "false_negatives": [
                {"comment": gc["comment"], "severity": gc.get("severity")}
                for gc in golden_comments
            ],
        }

    # Match each candidate against each golden comment
    golden_matched = {gc["comment"]: False for gc in golden_comments}
    candidate_matched = {c: False for c in candidates}
    true_positives = []

    for gc in golden_comments:
        tasks = [judge_match(gc["comment"], c) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            if result.get("match") and result.get("confidence", 0) >= 0.5:
                golden_matched[gc["comment"]] = True
                candidate_matched[candidates[i]] = True
                true_positives.append({
                    "golden": gc["comment"],
                    "severity": gc.get("severity"),
                    "candidate": candidates[i],
                    "confidence": result.get("confidence"),
                })
                break  # One match per golden is enough

    tp = sum(1 for v in golden_matched.values() if v)
    fp = sum(1 for v in candidate_matched.values() if not v)
    fn = sum(1 for v in golden_matched.values() if not v)

    precision = tp / len(candidates) if candidates else 0.0
    recall = tp / len(golden_comments) if golden_comments else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0,
        "total_candidates": len(candidates),
        "total_golden": len(golden_comments),
        "true_positives": true_positives,
        "false_negatives": [
            {"comment": gc["comment"], "severity": gc.get("severity")}
            for gc in golden_comments if not golden_matched[gc["comment"]]
        ],
    }


# ---------------------------------------------------------------------------
# Single model baseline
# ---------------------------------------------------------------------------

async def run_single_review(model: str, title: str, diff: str,
                            changed_files: list[str] | None = None) -> dict:
    """Run a single model code review and return extracted issues + timing."""
    start = time.time()
    diff_text = truncate_diff(diff)
    if changed_files:
        diff_text += f"\n\nChanged files: {', '.join(changed_files)}"
    prompt = REVIEW_PROMPT.format(title=title, diff=diff_text)
    try:
        review_text = await call_llm(model, prompt)
        issues = await extract_issues(review_text)
        elapsed = round(time.time() - start, 1)
        return {
            "model": model,
            "issues": issues,
            "num_issues": len(issues),
            "elapsed": elapsed,
            "review_text": review_text[:2000],
        }
    except Exception as e:
        return {
            "model": model,
            "issues": [],
            "num_issues": 0,
            "elapsed": round(time.time() - start, 1),
            "error": str(e)[:200],
        }


# ---------------------------------------------------------------------------
# Verd debate review
# ---------------------------------------------------------------------------

async def run_verd_review(title: str, diff: str, mode: str = "verd",
                          changed_files: list[str] | None = None) -> dict:
    """Run verd debate on a PR diff and return extracted issues."""
    start = time.time()
    claim = (
        f"Review this pull request for bugs, security issues, logic errors, "
        f"and correctness problems. PR: {title}"
    )
    context_parts = [f"```diff\n{truncate_diff(diff)}\n```"]
    if changed_files:
        context_parts.append(f"\nChanged files: {', '.join(changed_files)}")
    content = "\n".join(context_parts)
    try:
        result = await run_debate(content, claim, mode)
        # Extract issues same way as baselines — from the verdict text
        issues = result.get("issues", [])
        verdict_text = result.get("raw_verdict", "") or ""
        if not issues and verdict_text:
            issues = await extract_issues(verdict_text)

        elapsed = round(time.time() - start, 1)
        return {
            "model": "verd" if mode == "verd" else "verdh",
            "issues": issues,
            "num_issues": len(issues),
            "elapsed": elapsed,
            "cost": result.get("cost", 0),
            "confidence": result.get("confidence", 0),
            "consensus": result.get("consensus"),
            "model_votes": result.get("model_votes", {}),
        }
    except Exception as e:
        return {
            "model": "verd" if mode == "verd" else "verdh",
            "issues": [],
            "num_issues": 0,
            "elapsed": round(time.time() - start, 1),
            "error": str(e)[:200],
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Run verd against Martian Code Review Benchmark",
    )
    parser.add_argument("--mode", default="verdh", choices=["verd", "verdh"],
                        help="Debate mode (default: verdh)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max PRs to test (default: all 50)")
    parser.add_argument("--baselines", action="store_true",
                        help="Also run single-model baselines")
    parser.add_argument("--resume", action="store_true",
                        help="Skip PRs that already have results")
    args = parser.parse_args()

    # Load golden comments
    prs = load_golden_comments()
    print(f"Loaded {len(prs)} PRs with golden comments")
    print(f"Mode: {args.mode} | Baselines: {args.baselines} | Limit: {args.limit}")

    # Load existing results for resume
    results_file = RESULTS_DIR / f"results_{args.mode}.json"
    existing = {}
    if args.resume and results_file.exists():
        with open(results_file) as f:
            existing_list = json.load(f)
        existing = {r["pr_url"]: r for r in existing_list}
        print(f"Resuming: {len(existing)} PRs already done")

    results = list(existing.values())

    for i, pr in enumerate(prs[:args.limit]):
        pr_url = pr["url"]
        pr_title = pr["pr_title"]
        golden = pr["comments"]
        source = pr["_source_file"]

        if pr_url in existing:
            continue

        print(f"\n[{i+1}/{min(len(prs), args.limit)}] {source}/{pr_title}")
        print(f"  Golden comments: {len(golden)}")

        # Fetch diff + context
        print(f"  Fetching diff...", end="", flush=True)
        diff = fetch_pr_diff(pr_url)
        if not diff:
            print(f" FAILED (skipping)")
            results.append({
                "pr_url": pr_url, "pr_title": pr_title, "source": source,
                "golden_count": len(golden), "error": "Could not fetch diff",
            })
            continue
        time.sleep(2)  # Rate limit: avoid GitHub API 60 req/hr cap
        changed_files = fetch_changed_files(pr_url)
        time.sleep(2)
        print(f" {len(diff)} chars, {len(changed_files or [])} files")

        result = {
            "pr_url": pr_url,
            "pr_title": pr_title,
            "source": source,
            "golden_count": len(golden),
            "golden_comments": golden,
        }

        # Run baselines
        if args.baselines:
            for model in BASELINES:
                short = model.split("-")[0]
                print(f"  {short:12s}...", end="", flush=True)
                review = await run_single_review(model, pr_title, diff, changed_files)
                print(f" {review['num_issues']} issues | {review['elapsed']}s")
                # Evaluate
                eval_result = await evaluate_candidates(golden, review["issues"])
                review["evaluation"] = eval_result
                result[model] = review
                print(f"  {short:12s} P={eval_result['precision']:.0%} R={eval_result['recall']:.0%} F1={eval_result.get('f1', 0):.0%}")

        # Run verd (full debate)
        print(f"  {args.mode:12s}...", end="", flush=True)
        verd_review = await run_verd_review(pr_title, diff, args.mode, changed_files)
        print(f" {verd_review['num_issues']} issues | {verd_review['elapsed']}s"
              f" | {verd_review.get('consensus', '?')}")
        # Evaluate
        verd_eval = await evaluate_candidates(golden, verd_review["issues"])
        verd_review["evaluation"] = verd_eval
        result[args.mode] = verd_review
        print(f"  {args.mode:12s} P={verd_eval['precision']:.0%} R={verd_eval['recall']:.0%} F1={verd_eval.get('f1', 0):.0%}")

        if verd_eval.get("true_positives"):
            for tp in verd_eval["true_positives"]:
                print(f"    TP: {tp['golden'][:80]}...")

        results.append(result)

        # Save incrementally
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("MARTIAN CODE REVIEW BENCHMARK — FINAL RESULTS")
    print("=" * 70)

    modes = []
    if args.baselines:
        modes.extend(BASELINES)
    modes.append(args.mode)

    for mode in modes:
        valid = [r for r in results if mode in r and "evaluation" in r.get(mode, {})]
        if not valid:
            continue
        total_tp = sum(r[mode]["evaluation"]["tp"] for r in valid)
        total_fp = sum(r[mode]["evaluation"]["fp"] for r in valid)
        total_fn = sum(r[mode]["evaluation"]["fn"] for r in valid)
        total_candidates = sum(r[mode]["evaluation"]["total_candidates"] for r in valid)
        total_golden = sum(r[mode]["evaluation"]["total_golden"] for r in valid)
        avg_issues = sum(r[mode]["num_issues"] for r in valid) / len(valid)

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        print(f"\n  {mode}:")
        print(f"    PRs evaluated:  {len(valid)}")
        print(f"    Avg issues:     {avg_issues:.1f}")
        print(f"    Precision:      {precision:.1%}  ({total_tp} TP / {total_tp + total_fp} candidates)")
        print(f"    Recall:         {recall:.1%}  ({total_tp} TP / {total_golden} golden)")
        print(f"    F1:             {f1:.1%}")

    print(f"\nResults: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
