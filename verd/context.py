import fnmatch
import subprocess
import sys
from pathlib import Path

# Dirs/files to always skip
_SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".egg-info", ".eggs",
}
_SKIP_FILES = {
    ".DS_Store", "Thumbs.db", ".env", ".env.local",
}

MAX_CONTENT_CHARS = 200_000  # ~50k tokens, safe for most models

# Code extensions we care about
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".java",
    ".kt", ".swift", ".c", ".cpp", ".h", ".hpp", ".cs", ".php",
    ".scala", ".ex", ".exs", ".clj", ".lua", ".r", ".sql", ".sh",
    ".yaml", ".yml", ".toml", ".json", ".tf", ".hcl",
}


def _is_valid_path(p: Path) -> bool:
    if any(part in _SKIP_DIRS for part in p.parts):
        return False
    if p.name in _SKIP_FILES or p.name.startswith("."):
        return False
    return True


def _read_file(path: Path) -> str | None:
    """Read file content, return None on failure."""
    try:
        return path.read_text()
    except (UnicodeDecodeError, PermissionError):
        return None


def _collect_files(
    dir_path: Path,
    extensions: list[str] | None,
    excludes: list[str] | None,
) -> list[tuple[Path, str, str]]:
    """Collect files from directory. Returns list of (relative_path, content, extension).

    Auto-detects extensions if None.
    """
    if extensions is None:
        counts: dict[str, int] = {}
        for p in dir_path.rglob("*"):
            if not p.is_file() or not _is_valid_path(p):
                continue
            if p.suffix in _CODE_EXTENSIONS:
                counts[p.suffix] = counts.get(p.suffix, 0) + 1
        if not counts:
            return []
        extensions = sorted(counts, key=counts.get, reverse=True)
        pass  # auto-detected extensions

    files = []
    for p in sorted(dir_path.rglob("*")):
        if not p.is_file() or not _is_valid_path(p):
            continue
        if extensions and p.suffix not in extensions:
            continue
        if excludes and any(fnmatch.fnmatch(p.name, pat) for pat in excludes):
            continue

        text = _read_file(p)
        if text is None:
            continue

        rel = p.relative_to(dir_path)
        files.append((rel, text, p.suffix))

    return files


def files_to_content(files: list[tuple[Path, str, str]]) -> str:
    """Convert file list to concatenated content string with headers."""
    parts = []
    total = 0
    for path, text, _ext in files:
        chunk = f"--- {path} ---\n{text}\n"
        total += len(chunk)
        if total > MAX_CONTENT_CHARS:
            parts.append(f"\n[truncated at {MAX_CONTENT_CHARS // 1000}k chars]\n")
            break
        parts.append(chunk)
    return "\n".join(parts)


def _run_git(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git failed: {result.stderr.strip()}")
    return result.stdout


def build_context(args) -> tuple[str, str, list[tuple[Path, str, str]] | None]:
    """Returns (content, claim, files_or_none).

    When files is not None, content selection can be applied before debate.
    When files is None, content is already final (user picked it explicitly).
    """
    content = ""
    files = None

    if args.dir is not None:
        dir_path = Path(args.dir) if args.dir else Path(".")
        exts = args.ext or None
        excludes = args.exclude or None
        files = _collect_files(dir_path, exts, excludes)
        content = files_to_content(files)
    elif args.file:
        parts = []
        for f in args.file:
            p = Path(f)
            if not p.exists():
                print(f"warning: {f} not found, skipping", file=sys.stderr)
                continue
            text = _read_file(p)
            if text is not None:
                parts.append(f"--- {p.name} ---\n{text}\n")
        content = "\n".join(parts)
    elif args.git:
        content = _run_git(["git", "diff"])
    elif args.git_staged:
        content = _run_git(["git", "diff", "--staged"])
    elif args.git_branch:
        content = _run_git(["git", "diff", f"{args.git_branch}...HEAD"])
    elif args.context:
        content = args.context
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        # No content flag — auto-scan current directory
        cwd = Path(".")
        files = _collect_files(cwd, None, None)
        if files:
            content = files_to_content(files)

    content = content.strip()

    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + f"\n[truncated at {MAX_CONTENT_CHARS // 1000}k chars]"
        print(f"warning: content truncated to {MAX_CONTENT_CHARS // 1000}k chars", file=sys.stderr)

    return content, args.claim.strip(), files
