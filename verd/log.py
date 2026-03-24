"""Structured logging for verd.

Usage:
    import logging
    log = logging.getLogger("verd.engine")
    log.warning("model %s failed: %s", model, error)

Log output goes to stderr so it doesn't interfere with --json or piped output.
"""

import logging
import sys


def setup(level: int = logging.WARNING) -> None:
    """Configure verd loggers. Call once at startup."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    root = logging.getLogger("verd")
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)
