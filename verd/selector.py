"""Smart context selection — picks relevant files using keyword matching + dependency walking.

Falls back to LLM selection only for ambiguous queries.
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from verd.config import get_client, JSON_MODE_MODELS

# LLM fallback config
SELECTOR_MODEL = "gpt-5-mini"
SELECTOR_TIMEOUT = 30
SELECTOR_MAX_TOKENS = 2048

# Only trigger selection when we have more than this many files
MIN_FILES_FOR_SELECTION = 5
MAX_SELECTED_FILES = 15

# Words to ignore when extracting keywords from the claim
_STOP_WORDS = {
    "any", "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "can", "shall", "this", "that", "these", "those", "it", "its",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "or", "and",
    "not", "no", "but", "if", "then", "so", "up", "out", "about", "into", "over",
    "after", "before", "between", "under", "during", "without", "through",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "only", "own", "same", "than", "too", "very", "just", "also",
    "how", "what", "where", "when", "why", "who", "which",
    "good", "bad", "well", "better", "best", "use", "using", "used",
    "need", "want", "make", "get", "find", "look", "see", "know",
    "code", "codes", "file", "files", "py", "python", "check", "review",
    "there", "here", "my", "our", "your", "their", "me", "we", "you", "they",
}


def _extract_keywords(claim: str) -> list[str]:
    """Extract meaningful keywords from the claim."""
    words = re.findall(r'[a-z][a-z0-9_]+', claim.lower())
    keywords = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    # Also extract multi-word patterns (e.g. "growth_model", "churn model" -> "churn_model")
    # by looking for adjacent keywords that might form a compound
    return list(dict.fromkeys(keywords))  # dedupe preserving order


def _extract_imports_from_content(content: str, ext: str) -> set[str]:
    """Extract local import names from file content."""
    imports = set()
    if ext == ".py":
        for m in re.finditer(r'^(?:from|import)\s+(\w+)', content, re.MULTILINE):
            imports.add(m.group(1))
        # Also catch "from .foo import bar" and "from foo.bar import baz"
        for m in re.finditer(r'^from\s+\.?(\w+)', content, re.MULTILINE):
            imports.add(m.group(1))
    elif ext in (".js", ".ts", ".tsx", ".jsx"):
        for m in re.finditer(r'''(?:from|require\()\s*['"]\.?\.?/?(\w+)''', content):
            imports.add(m.group(1))
    return imports


def _score_file(
    path: Path,
    content: str,
    ext: str,
    keywords: list[str],
) -> float:
    """Score a file's relevance to the keywords. Higher = more relevant."""
    score = 0.0
    path_str = str(path).lower()
    stem = path.stem.lower()
    content_lower = content.lower()

    for kw in keywords:
        # Filename/path match — strongest signal
        if kw in stem:
            score += 10.0
        elif kw in path_str:
            score += 7.0

        # Function/class name match
        if ext == ".py":
            # Match def kw_something or class KwSomething
            if re.search(rf'\b(?:def|class)\s+\w*{re.escape(kw)}\w*', content_lower):
                score += 5.0
        elif ext in (".js", ".ts", ".tsx", ".jsx"):
            if re.search(rf'\b(?:function|const|class)\s+\w*{re.escape(kw)}\w*', content_lower):
                score += 5.0

        # Content mention — weakest but still relevant
        count = content_lower.count(kw)
        if count > 0:
            score += min(count * 0.5, 3.0)  # cap at 3

    return score


def _find_dependencies(
    selected_indices: set[int],
    files: list[tuple[Path, str, str]],
) -> set[int]:
    """Walk imports of selected files and add any local files they depend on."""
    # Build a map of module name -> file index
    module_map: dict[str, int] = {}
    for i, (path, _content, ext) in enumerate(files):
        stem = path.stem.lower()
        module_map[stem] = i
        # Also map by full dotted path (e.g. auth/jwt_handler -> auth.jwt_handler)
        dotted = str(path).replace("/", ".").replace("\\", ".")
        if dotted.endswith(ext):
            dotted = dotted[:-len(ext)]
        module_map[dotted.lower()] = i

    deps = set(selected_indices)
    to_check = list(selected_indices)

    while to_check:
        idx = to_check.pop()
        _path, content, ext = files[idx]
        imports = _extract_imports_from_content(content, ext)
        for imp in imports:
            imp_lower = imp.lower()
            if imp_lower in module_map:
                dep_idx = module_map[imp_lower]
                if dep_idx not in deps:
                    deps.add(dep_idx)
                    to_check.append(dep_idx)

    return deps


def select_by_keywords(
    files: list[tuple[Path, str, str]],
    claim: str,
) -> list[int] | None:
    """Score and select files using keyword matching. Returns 0-indexed list or None if no matches."""
    keywords = _extract_keywords(claim)
    if not keywords:
        return None

    # Score all files
    scored = []
    for i, (path, content, ext) in enumerate(files):
        score = _score_file(path, content, ext, keywords)
        if score > 0:
            scored.append((i, score))

    if not scored:
        return None

    # Take files scoring above threshold (at least a filename partial match)
    scored.sort(key=lambda x: x[1], reverse=True)
    # Use top-scoring files + anything scoring > 3 (at least a function name match)
    top_score = scored[0][1]
    threshold = max(3.0, top_score * 0.2)
    primary = {i for i, s in scored if s >= threshold}

    if not primary:
        return None

    # Walk dependencies of selected files
    with_deps = _find_dependencies(primary, files)

    indices = sorted(with_deps)[:MAX_SELECTED_FILES]

    selected_names = [str(files[i][0]) for i in indices]
    print(
        f"selected {len(indices)}/{len(files)} files: {', '.join(selected_names)}",
        file=sys.stderr,
    )
    return indices


# --- LLM fallback (only used when keyword matching finds nothing) ---

def _extract_signatures(text: str, ext: str) -> list[str]:
    sigs = []
    if ext in (".py",):
        for m in re.finditer(r"^(class \w+.*?:|def \w+\(.*?\).*?:)", text, re.MULTILINE):
            sigs.append(m.group(1).strip())
    elif ext in (".js", ".ts", ".tsx", ".jsx"):
        for m in re.finditer(
            r"^(?:export\s+)?(?:async\s+)?(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\()",
            text, re.MULTILINE,
        ):
            sigs.append(m.group(0).strip()[:100])
    return sigs[:20]


def _build_manifest(files: list[tuple[Path, str, str]]) -> str:
    parts = []
    for i, (path, content, ext) in enumerate(files, 1):
        lines = content.split("\n")
        imports = []
        for line in lines[:30]:
            line = line.strip()
            if ext == ".py" and (line.startswith("import ") or line.startswith("from ")):
                mod = line.split()[1].split(".")[0]
                if mod not in imports:
                    imports.append(mod)
        sigs = _extract_signatures(content, ext)[:10]

        entry = f"[{i}] {path} ({len(lines)} lines)"
        if imports:
            entry += f"\n    imports: {', '.join(imports[:8])}"
        if sigs:
            entry += "\n    " + "\n    ".join(sigs)
        parts.append(entry)
    return "\n\n".join(parts)


async def _select_by_llm(
    files: list[tuple[Path, str, str]],
    claim: str,
) -> list[int] | None:
    """LLM-based fallback. Returns 0-indexed list or None."""
    manifest = _build_manifest(files)
    prompt = (
        "You are a file selector. Pick files relevant to the question.\n\n"
        "Rules:\n"
        "- Select files that directly relate to the question\n"
        "- Include files imported by relevant files\n"
        "- Return ONLY the file numbers in the selected array\n\n"
        f'Question: "{claim}"\n\n'
        f"Files:\n{manifest}\n\n"
        'Respond with JSON: {"selected": [1, 3, 7], "reason": "brief explanation"}'
    )

    try:
        kwargs = {
            "model": SELECTOR_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": SELECTOR_MAX_TOKENS,
        }
        if SELECTOR_MODEL in JSON_MODE_MODELS:
            kwargs["response_format"] = {"type": "json_object"}

        response = await asyncio.wait_for(
            get_client().chat.completions.create(**kwargs),
            timeout=SELECTOR_TIMEOUT,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            cleaned = re.sub(r"```json|```", "", text).strip()
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                return None

        reason = data.get("reason", "")
        if reason:
            print(f"selector (llm): {reason}", file=sys.stderr)

        selected = data.get("selected", [])
        # Convert to 0-indexed
        indices = [i - 1 for i in selected if isinstance(i, int) and 1 <= i <= len(files)]
        if indices:
            names = [str(files[i][0]) for i in indices]
            print(f"selected {len(indices)}/{len(files)} files: {', '.join(names)}", file=sys.stderr)
        return indices if indices else None

    except Exception as e:
        print(f"\u26a0 selector llm failed: {e}", file=sys.stderr)
        return None


async def select_relevant_files(
    files: list[tuple[Path, str, str]],
    claim: str,
    status_callback=None,
) -> list[tuple[Path, str, str]]:
    """Pick relevant files. Keyword match first, LLM fallback if no matches."""
    if len(files) <= MIN_FILES_FOR_SELECTION:
        return files

    if status_callback:
        status_callback("selecting relevant files...")

    # 1. Fast keyword matching (no API call)
    indices = select_by_keywords(files, claim)

    # 2. LLM fallback if keywords found nothing
    if indices is None:
        if status_callback:
            status_callback("keyword match inconclusive, asking model...")
        indices_0 = await _select_by_llm(files, claim)
        if indices_0 is not None:
            return [files[i] for i in indices_0[:MAX_SELECTED_FILES]]
        print("selector: no relevant files found, using all", file=sys.stderr)
        return files

    return [files[i] for i in indices]
