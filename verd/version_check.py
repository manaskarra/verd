"""Lightweight PyPI version check with 24h cache."""

import json
import os
import sys
import time
import urllib.request

from verd.config import VERSION

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "verd")
CACHE_FILE = os.path.join(CACHE_DIR, "version.json")
SETUP_MARKER = os.path.join(CACHE_DIR, ".setup_shown")
CACHE_TTL = 86400  # 24 hours
PYPI_URL = "https://pypi.org/pypi/verd/json"
TIMEOUT = 2  # seconds — don't slow down CLI
MIN_VERSION = "0.3.6"  # hard minimum — older versions are blocked


def _parse_version(v: str):
    """Parse version string into tuple for comparison."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except (ValueError, AttributeError):
        return (0,)


def _read_cache():
    """Read cached latest version if fresh enough."""
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) < CACHE_TTL:
            return data.get("version")
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return None


def _write_cache(version: str):
    """Cache the latest version."""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"version": version, "ts": time.time()}, f)
    except OSError:
        pass


def _fetch_latest():
    """Fetch latest version from PyPI."""
    try:
        req = urllib.request.Request(PYPI_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


def check_version():
    """Block outdated versions, or print upgrade notice for newer ones."""
    # Hard block for versions below minimum
    if _parse_version(VERSION) < _parse_version(MIN_VERSION):
        print(
            f"\n  verd {VERSION} is no longer supported."
            f"\n  Please upgrade: pip install -U verd\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # Soft notice for newer versions available
    try:
        latest = _read_cache()
        if latest is None:
            latest = _fetch_latest()
            if latest:
                _write_cache(latest)

        if latest and _parse_version(latest) > _parse_version(VERSION):
            print(
                f"\n  Update available: verd {VERSION} -> {latest}"
                f"\n  Run: pip install -U verd\n",
                file=sys.stderr,
            )
    except Exception:
        pass  # never break the CLI for a version check

    # First-run setup hint — shown once per install
    try:
        if not os.path.exists(SETUP_MARKER):
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(SETUP_MARKER, "w") as f:
                f.write(VERSION)
            print(
                f"\n  Welcome to verd {VERSION}!"
                f"\n  Run: verd setup"
                f"\n  to configure verd CLI or MCP server.\n",
                file=sys.stderr,
            )
    except OSError:
        pass
