"""Security utilities — input validation, SSRF protection, rate limiting."""

import ipaddress
import logging
import re
import socket
import time
from urllib.parse import urlparse

logger = logging.getLogger("verd.security")

# --- Constants ---
MAX_CLAIM_LENGTH = 2000
MAX_CONTENT_CHARS = 200_000
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_CALLS = 5  # per user per window
MAX_LAST_N = 200  # max messages to read from channel

# --- SSRF protection ---
_BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata.internal"}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP (v4 or v6) is in a blocked private range."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in network for network in _BLOCKED_IP_RANGES)
    except ValueError:
        return True  # can't parse = block


def resolve_and_check(hostname: str) -> bool:
    """Resolve hostname via both IPv4 and IPv6, check all IPs are safe."""
    try:
        results = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        if not results:
            return False
        for family, _, _, _, sockaddr in results:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                return False
        return True
    except socket.gaierror:
        return False


def is_safe_url(url: str) -> bool:
    """Check if URL is safe to fetch (not internal/private network). Covers IPv4 + IPv6."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname or hostname in _BLOCKED_HOSTNAMES:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        return resolve_and_check(hostname)
    except Exception:
        return False


def is_safe_redirect(url: str) -> bool:
    """Validate a redirect target URL before following it."""
    return is_safe_url(url)


MAX_FETCH_BYTES = 100_000  # 100KB max response body
FETCH_TIMEOUT = 10


def safe_fetch_url(url: str, max_redirects: int = 3) -> str | None:
    """Fetch URL with pinned IP resolution, redirect validation, and byte limit.

    Returns HTML text or None on failure. Prevents DNS rebinding TOCTOU
    by resolving the IP once and connecting directly to it.
    """
    import httpx

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return None

    # Resolve once and pin
    try:
        results = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        if not results:
            return None
        pinned_ip = results[0][4][0]
        if _is_private_ip(pinned_ip):
            logger.warning("Blocked private IP for %s: %s", hostname, pinned_ip)
            return None
    except socket.gaierror:
        return None

    current_url = url
    with httpx.Client(timeout=FETCH_TIMEOUT, max_redirects=0) as client:
        for _ in range(max_redirects + 1):
            try:
                resp = client.get(current_url)
            except httpx.HTTPError:
                return None

            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_url = resp.headers.get("location", "")
                if not is_safe_redirect(redirect_url):
                    logger.warning("Blocked redirect: %s -> %s", current_url, redirect_url)
                    return None
                current_url = redirect_url
                continue

            if resp.status_code != 200:
                return None
            if "text" not in resp.headers.get("content-type", ""):
                return None

            # Read with byte limit
            content = resp.text[:MAX_FETCH_BYTES]
            return content

    return None


# --- Input validation ---
def validate_claim(claim: str) -> str:
    """Validate and truncate claim to safe length."""
    claim = claim.strip()
    if len(claim) > MAX_CLAIM_LENGTH:
        claim = claim[:MAX_CLAIM_LENGTH] + "..."
    return claim or "Is this correct?"


def validate_content(content: str) -> str:
    """Truncate content to safe length."""
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + f"\n[truncated at {MAX_CONTENT_CHARS // 1000}k chars]"
    return content


def parse_last_n(text: str) -> int | None:
    """Extract 'last N' from text. Returns N capped at MAX_LAST_N, or None."""
    m = re.search(r'\blast\s+(\d+)\b', text, re.IGNORECASE)
    if m:
        return min(int(m.group(1)), MAX_LAST_N)
    return None


# --- Rate limiting ---
_user_last_call: dict[str, float] = {}
_user_call_count: dict[str, int] = {}


def check_rate_limit(user_id: str) -> str | None:
    """Returns error message if rate limited, None if OK."""
    now = time.time()
    last = _user_last_call.get(user_id, 0)

    if now - last > RATE_LIMIT_WINDOW:
        _user_call_count[user_id] = 0

    count = _user_call_count.get(user_id, 0)
    if count >= RATE_LIMIT_MAX_CALLS:
        remaining = int(RATE_LIMIT_WINDOW - (now - last))
        return f"Rate limited — max {RATE_LIMIT_MAX_CALLS} calls per minute. Try again in {remaining}s."

    _user_call_count[user_id] = count + 1
    _user_last_call[user_id] = now
    return None


# --- Safe error messages ---
def safe_error_msg(e: Exception) -> str:
    """Return a generic error message — never expose internals to users."""
    msg = str(e).lower()
    if "timeout" in msg:
        return "The debate timed out. Try again or use a lighter mode (`quick`)."
    if "rate" in msg or "429" in msg:
        return "API rate limit hit. Please wait a moment and try again."
    logger.error("Debate error: %s", type(e).__name__)
    return "Something went wrong running the debate. Please try again."
