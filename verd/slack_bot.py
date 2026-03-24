"""Slack bot for verd — reads thread context, runs debate, replies in thread."""

import asyncio
import os
import re
import ssl
import time
import logging
from html.parser import HTMLParser

import certifi
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient

from verd.engine import run_debate
from verd.security import (
    check_rate_limit, is_safe_url, validate_claim, validate_content,
    parse_last_n, safe_error_msg,
)

logger = logging.getLogger("verd.slack")

# --- Startup validation ---
_REQUIRED_ENV = {
    "SLACK_BOT_TOKEN": "xoxb-...",
    "SLACK_APP_TOKEN": "xapp-...",
    "SLACK_SIGNING_SECRET": "from Slack app Basic Information",
    "OPENAI_API_KEY": "LiteLLM/OpenRouter/OpenAI key",
    "OPENAI_BASE_URL": "API base URL",
}

for _var, _hint in _REQUIRED_ENV.items():
    if not os.environ.get(_var):
        raise EnvironmentError(f"{_var} is not set. Expected: {_hint}")

ssl_context = ssl.create_default_context(cafile=certifi.where())

app = App(
    client=WebClient(token=os.environ["SLACK_BOT_TOKEN"], ssl=ssl_context),
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
)

DEFAULT_CHANNEL_MESSAGES = 20


# --- Authorization ---
# Optional: set env vars to restrict who/where can use verd
# VERD_ALLOWED_CHANNELS=C123,C456 (comma-separated channel IDs, empty = all)
# VERD_ALLOWED_USERS=U123,U456 (comma-separated user IDs, empty = all)
_ALLOWED_CHANNELS = set(filter(None, os.environ.get("VERD_ALLOWED_CHANNELS", "").split(",")))
_ALLOWED_USERS = set(filter(None, os.environ.get("VERD_ALLOWED_USERS", "").split(",")))


def _check_auth(user_id: str, channel_id: str) -> str | None:
    """Returns error if user/channel not authorized, None if OK."""
    if _ALLOWED_USERS and user_id not in _ALLOWED_USERS:
        return "You're not authorized to use verd."
    if _ALLOWED_CHANNELS and channel_id not in _ALLOWED_CHANNELS:
        return "verd is not enabled in this channel."
    return None


# --- Slack context helpers ---

def _resolve_user_names(client, user_ids: set[str]) -> dict[str, str]:
    names = {}
    for uid in user_ids:
        try:
            info = client.users_info(user=uid)
            profile = info["user"]["profile"]
            names[uid] = profile.get("display_name") or profile.get("real_name") or uid
        except Exception:
            names[uid] = uid
    return names


def _get_user_names(client, messages: list[dict], bot_user_id: str) -> dict[str, str]:
    user_ids = set()
    for msg in messages:
        uid = msg.get("user", "")
        if uid and uid != bot_user_id:
            user_ids.add(uid)
        for mention in re.findall(r"<@(\w+)>", msg.get("text", "")):
            user_ids.add(mention)
    return _resolve_user_names(client, user_ids)


def _messages_to_context(messages: list[dict], bot_user_id: str, user_names: dict[str, str]) -> list[str]:
    parts = []
    for msg in messages:
        user = msg.get("user", "unknown")
        text = msg.get("text", "")
        if user == bot_user_id:
            continue

        def replace_mention(m):
            return f"@{user_names.get(m.group(1), m.group(1))}"
        text = re.sub(r"<@(\w+)>", replace_mention, text).strip()
        if not text:
            continue

        for f in msg.get("files", []):
            preview = f.get("preview") or f.get("plain_text")
            if preview:
                text += f"\n\n```\n{preview}\n```"

        parts.append(f"[{user_names.get(user, user)}]: {text}")
    return parts


def _get_thread_context(client, channel: str, thread_ts: str, bot_user_id: str) -> tuple[str, str]:
    result = client.conversations_replies(channel=channel, ts=thread_ts, limit=50)
    messages = result.get("messages", [])
    user_names = _get_user_names(client, messages, bot_user_id)
    parts = _messages_to_context(messages, bot_user_id, user_names)
    return "\n\n---\n\n".join(parts), f"thread ({len(parts)} messages)"


def _get_channel_context(client, channel: str, before_ts: str, bot_user_id: str,
                         limit: int = DEFAULT_CHANNEL_MESSAGES) -> tuple[str, str]:
    result = client.conversations_history(channel=channel, latest=before_ts, limit=limit + 1, inclusive=False)
    messages = result.get("messages", [])
    has_more = result.get("has_more", False) or len(messages) > limit
    messages = messages[:limit]
    messages.reverse()
    user_names = _get_user_names(client, messages, bot_user_id)
    parts = _messages_to_context(messages, bot_user_id, user_names)

    label = f"last {len(parts)} messages"
    if has_more and limit == DEFAULT_CHANNEL_MESSAGES:
        label += " (say `last 50` or `last 100` for more)"
    return "\n\n---\n\n".join(parts), label


class _TextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping script/style/nav."""
    def __init__(self):
        super().__init__()
        self.text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data.strip())


def _fetch_urls(text: str) -> str:
    """Extract and fetch URLs from text. SSRF-safe."""
    urls = re.findall(r"<(https?://[^>|]+)(?:\|[^>]*)?>", text)
    if not urls:
        return ""

    from verd.security import safe_fetch_url

    extra = []
    for url in urls[:3]:
        if not is_safe_url(url):
            logger.warning("Blocked unsafe URL: %s", url)
            continue
        try:
            html = safe_fetch_url(url)
            if html:
                parser = _TextExtractor()
                parser.feed(html)
                page_text = " ".join(t for t in parser.text if t)[:5000]
                if page_text:
                    extra.append(f"--- Content from {url} ---\n{page_text}")
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, type(e).__name__)

    return "\n\n".join(extra)


# --- Slack formatting ---

_SLACK_LABELS = {"PASS": "SUPPORTED", "FAIL": "CHALLENGED", "UNCERTAIN": "MIXED"}
_SLACK_EMOJI = {"PASS": ":white_check_mark:", "FAIL": ":no_entry_sign:", "UNCERTAIN": ":scales:"}
_REACTION_EMOJI = {"PASS": "white_check_mark", "FAIL": "no_entry_sign", "UNCERTAIN": "scales"}
_MODE_HINTS = {
    "verdl": "_Say `deep` for deeper analysis with 5 models + web search_",
    "verd": "_Say `deep` for 5-model analysis with web search, or `quick` for a fast check_",
    "verdh": "_This was a deep analysis (5 models, 3 rounds, web search)_",
}


def _format_verdict_blocks(result: dict) -> list[dict]:
    verdict = result.get("verdict", "UNCERTAIN")
    label = _SLACK_LABELS.get(verdict, "MIXED")
    confidence = int(result.get("confidence", 0) * 100)
    headline = result.get("headline") or result.get("summary", "")
    strengths = result.get("strengths", [])
    issues = result.get("issues", [])
    fixes = result.get("fixes", [])
    mode = result.get("mode", "verd")
    elapsed = result.get("elapsed", 0)
    cost = result.get("cost", 0)
    emoji = _SLACK_EMOJI.get(verdict, ":grey_question:")

    model_votes = result.get("model_votes", {})
    unique_catches = result.get("unique_catches", [])
    dissent = result.get("dissent")

    # Vote line
    vote_emojis = {"PASS": ":white_check_mark:", "FAIL": ":x:", "UNCERTAIN": ":grey_question:"}
    vote_line = "  ".join(
        f"{m.split('-')[0]} {vote_emojis.get(v, ':grey_question:')}"
        for m, v in model_votes.items()
    ) if model_votes else ""

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{label}  {confidence}%", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{emoji} *{headline}*"}},
    ]

    if vote_line:
        consensus = result.get("consensus", "")
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"{vote_line}  _{consensus}_"}]})

    if strengths:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
            "*Strengths*\n" + "\n".join(f":large_green_circle: {s}" for s in strengths)}})
    if issues:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
            "*Issues*\n" + "\n".join(f":red_circle: {i}" for i in issues)}})
    if unique_catches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
            "*Unique Catches*\n" + "\n".join(f":mag: {c}" for c in unique_catches)}})
    if fixes:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
            "*Fixes*\n" + "\n".join(f":arrow_right: {f}" for f in fixes)}})
    if dissent:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
            f":speech_balloon: *Dissent:* {dissent[:300]}"}})

    footer = f"_{mode} • {len(result.get('models_used', []))} models • {elapsed}s"
    if cost:
        footer += f" • ~${cost:.2f}"
    footer += "_"

    footer_parts = [footer]

    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " | ".join(footer_parts)}]})
    if mode in _MODE_HINTS:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _MODE_HINTS[mode]}]})

    return blocks


# --- Shared helpers ---

def _pick_mode(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("verdh", "heavy", "deep")):
        return "verdh"
    if any(w in t for w in ("verdl", "light", "quick")):
        return "verdl"
    return "verd"


def _extract_claim(text: str, bot_user_id: str) -> str:
    claim = re.sub(rf"<@{bot_user_id}>", "", text).strip()
    claim = re.sub(r"\b(verdh|verdl|verd|heavy|light|quick|deep)\b", "", claim, flags=re.IGNORECASE).strip()
    claim = re.sub(r'\blast\s+\d+\b', '', claim, flags=re.IGNORECASE).strip()
    claim = re.sub(r"\s+", " ", claim).strip()
    return validate_claim(claim)


def _build_context(client, event, bot_user_id, text):
    """Build content and source_label from thread or channel."""
    is_thread = event.get("thread_ts") is not None
    last_n = parse_last_n(text)

    if is_thread:
        content, source_label = _get_thread_context(client, event["channel"], event["thread_ts"], bot_user_id)
    else:
        limit = last_n or DEFAULT_CHANNEL_MESSAGES
        content, source_label = _get_channel_context(client, event["channel"], event["ts"], bot_user_id, limit)

    url_context = _fetch_urls(f"{text}\n{content}")
    if url_context:
        content = f"{content}\n\n{url_context}" if content else url_context

    return validate_content(content), source_label, is_thread


# --- Event handlers ---

@app.event("app_mention")
def handle_mention(event, client, say):
    user_id = event["user"]
    channel = event["channel"]
    text = event.get("text", "")
    thread_ts = event.get("thread_ts")

    auth_err = _check_auth(user_id, channel)
    if auth_err:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts or event["ts"],
                                text=f":no_entry_sign: {auth_err}")
        return

    rate_err = check_rate_limit(user_id)
    if rate_err:
        client.chat_postMessage(channel=channel, thread_ts=thread_ts or event["ts"],
                                text=f":warning: {rate_err}")
        return

    auth = client.auth_test()
    bot_user_id = auth["user_id"]
    claim = _extract_claim(text, bot_user_id)
    mode = _pick_mode(text)

    client.reactions_add(channel=channel, timestamp=event["ts"], name="thinking_face")

    try:
        content, source_label, is_thread = _build_context(client, event, bot_user_id, text)
        logger.info(f"user={user_id} mode={mode} source={source_label} content_len={len(content)}")

        result = asyncio.run(run_debate(content, claim, mode))

        blocks = _format_verdict_blocks(result)
        blocks.insert(0, {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"_{claim}_ | {source_label}"}]})

        reply_ts = thread_ts if is_thread else event["ts"]
        client.chat_postMessage(channel=channel, thread_ts=reply_ts, blocks=blocks,
                                text=f"{result.get('verdict', 'UNCERTAIN')} — {result.get('headline', '')}")

        client.reactions_remove(channel=channel, timestamp=event["ts"], name="thinking_face")
        emoji = _REACTION_EMOJI.get(result.get("verdict", "UNCERTAIN"), "grey_question")
        client.reactions_add(channel=channel, timestamp=event["ts"], name=emoji)

    except Exception as e:
        logger.exception("Mention handler failed")
        client.reactions_remove(channel=channel, timestamp=event["ts"], name="thinking_face")
        client.reactions_add(channel=channel, timestamp=event["ts"], name="x")
        try:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts or event["ts"],
                                    text=f":warning: {safe_error_msg(e)}")
        except Exception:
            pass


@app.event("message")
def handle_dm(event, client):
    if event.get("channel_type") != "im" or event.get("bot_id"):
        return

    user_id = event["user"]
    channel = event["channel"]
    text = event.get("text", "")

    if _ALLOWED_USERS and user_id not in _ALLOWED_USERS:
        client.chat_postMessage(channel=channel, text=":no_entry_sign: You're not authorized to use verd.")
        return

    rate_err = check_rate_limit(user_id)
    if rate_err:
        client.chat_postMessage(channel=channel, text=f":warning: {rate_err}")
        return

    claim = validate_claim(text.strip())
    mode = _pick_mode(text)
    client.reactions_add(channel=channel, timestamp=event["ts"], name="thinking_face")

    try:
        result = asyncio.run(run_debate("", claim, mode))
        client.chat_postMessage(channel=channel, blocks=_format_verdict_blocks(result),
                                text=f"{result.get('verdict', 'UNCERTAIN')}")
        client.reactions_remove(channel=channel, timestamp=event["ts"], name="thinking_face")
    except Exception as e:
        logger.exception("DM handler failed")
        client.chat_postMessage(channel=channel, text=f":warning: {safe_error_msg(e)}")


# --- Slash commands ---

def _handle_slash(ack, command, respond, client, mode: str):
    from verd.models import MODELS
    cfg = MODELS[mode]
    user_id = command["user_id"]

    channel = command["channel_id"]

    auth_err = _check_auth(user_id, channel)
    if auth_err:
        ack(f":no_entry_sign: {auth_err}")
        return

    rate_err = check_rate_limit(user_id)
    if rate_err:
        ack(f":warning: {rate_err}")
        return

    ack(f":thinking_face: Spawning {len(cfg['debaters'])} models: {', '.join(cfg['debaters'])}...")
    claim = validate_claim(command.get("text", "").strip())

    def status_update(msg):
        try:
            respond(f":thinking_face: {msg}", replace_original=True)
        except Exception:
            pass

    try:
        auth = client.auth_test()
        bot_user_id = auth["user_id"]
        content, source_label = _get_channel_context(client, channel, str(time.time()), bot_user_id)
        if not content:
            source_label = "no context"

        content = validate_content(content)
        status_update(f"Reading {source_label}, debating...")

        async def on_status(msg):
            status_update(msg)

        result = asyncio.run(run_debate(content, claim, mode, status_callback=on_status))
        respond(delete_original=True)

        blocks = _format_verdict_blocks(result)
        blocks.insert(0, {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"_{claim}_ | {source_label} | <@{user_id}>"}]})

        client.chat_postMessage(channel=channel, blocks=blocks,
                                text=f"{result.get('verdict', 'UNCERTAIN')} — {result.get('headline', '')}")

    except Exception as e:
        logger.exception("Slash command failed")
        client.chat_postMessage(channel=channel, text=f":warning: {safe_error_msg(e)}")


@app.command("/verd")
def slash_verd(ack, command, respond, client):
    _handle_slash(ack, command, respond, client, "verd")

@app.command("/verdl")
def slash_verdl(ack, command, respond, client):
    _handle_slash(ack, command, respond, client, "verdl")

@app.command("/verdh")
def slash_verdh(ack, command, respond, client):
    _handle_slash(ack, command, respond, client, "verdh")


def main():
    logging.basicConfig(level=logging.INFO)
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    logger.info("verd Slack bot starting...")
    handler.start()


if __name__ == "__main__":
    main()
