# verd

**Five minds enter. They argue, challenge, cross-examine. Only the truth walks out.**

verd spawns multiple AI models from different families — each with a specialized role — has them debate your question across rounds, then a stronger judge delivers the final verdict with strengths, issues, and actionable fixes.

Use it everywhere: **CLI** for code reviews, **MCP** inside Claude Code and Cursor, **Slack** as `@verd` in any conversation, or **pipe** anything into it.

## Install

```bash
pip install verd
```

## Setup

verd talks to any OpenAI-compatible API. Set two env vars (or put them in a `.env` file):

```bash
export OPENAI_API_KEY=your-key
export OPENAI_BASE_URL=https://openrouter.ai/api/v1  # or any compatible endpoint
```

Works with [OpenRouter](https://openrouter.ai) (easiest — all models, one key), direct OpenAI, [LiteLLM proxy](https://docs.litellm.ai/), Azure, Together, Groq, etc.

## Usage

```bash
verd "Kafka or RabbitMQ for our event pipeline?" -f architecture.md
verd "can this auth middleware be bypassed?" -f auth.py middleware.py
verdh "should we merge this?" -gb main
verdl "is O(n^2) acceptable for n=1000?"
cat deploy.yaml | verd "any misconfigs that could expose prod?"
```

## Output

```
FAIL  77%  In-memory rate limiter is unsafe for production

claude:FAIL  gpt:FAIL  gemini:FAIL  gpt:FAIL  (FULL)

+ Conceptually correct sliding-window logic
- Global dict is unsynchronized — race conditions in multi-thread servers
- Per-user lists grow without bounds — memory leak / DoS vector
! gpt-5-mini caught the risk of system clock jumps with time.time()
→ Move state to Redis with atomic operations

completed in 69.3s • 22,449 tokens • ~$0.07
```

Vote breakdown, unique catches (`!`), dissent, strengths, issues, and actionable fixes — all in one view.

## Modes

| Command | Debaters | Roles | Rounds | Speed | Cost |
|---------|----------|-------|--------|-------|------|
| `verdl` | 2 + judge | analyst, devils_advocate | 1 | ~15-30s | ~$0.02 |
| `verd` | 4 + judge | analyst, devils_advocate, logic_checker, pragmatist | 2 | ~30-60s | ~$0.15+ |
| `verdh` | 5 + judge + web | analyst, devils_advocate, logic_checker, fact_checker, pragmatist | 3 | ~60-120s | ~$0.40+ |

## How it works

1. Your question + content gets sent to multiple AI models in parallel
2. Each model has a **specialized role** (analyst, devils_advocate, logic_checker, fact_checker, pragmatist)
3. Models see each other's responses and cross-examine for 1-3 rounds
4. **Anti-groupthink prompts** ensure models hold their ground when they have evidence — consensus without new evidence is rejected
5. A stronger judge model synthesizes the debate, weighting each reviewer by their role
6. **Confidence is calculated from vote distribution** — a fact_checker's dissent lowers confidence more than a devils_advocate's expected pushback
7. You get: verdict, vote breakdown, strengths, issues, unique catches, dissent, and actionable fixes

The key insight: different models have different blind spots. Claude spots nuance GPT misses. Gemini catches logic errors DeepSeek overlooks. The debate surfaces all of them — and tells you exactly which model caught what.

## Roles

| Role | Job | Example catch |
|------|-----|---------------|
| **analyst** | Balanced initial assessment, main arguments for and against | "The architecture is sound but the auth flow has a gap" |
| **devils_advocate** | Find what others miss — edge cases, hidden assumptions, failure modes | "What happens when the token expires mid-transaction?" |
| **logic_checker** | Verify reasoning quality — fallacies, off-by-one, race conditions | "The pagination math is wrong: total_pages needs ceil division" |
| **fact_checker** | Web-grounded verification — do these APIs/libraries actually work? | "That library was deprecated in v3, use the new API" |
| **pragmatist** | Real-world practicality — will this ship? What's the ops burden? | "This works but needs 3 new infra dependencies your team doesn't know" |

The judge weighs each reviewer's input by role — a fact_checker citing sources carries more weight than a devils_advocate pushing back.

## Config

Customize models via `~/.verd.yaml`, env vars (`VERD_JUDGE`, `VERD_DEBATERS`, `VERD_BUDGET`, `VERD_TIMEOUT`), or CLI flags. Precedence: CLI > env > file > defaults.

```yaml
# ~/.verd.yaml
judge: gpt-5.4
debaters: claude-sonnet-4-6, gpt-4.1, gemini-2.5-flash
budget: 1.00
```

## Flags

```
-f FILE [FILE ...]    files to review         -g / -gs / -gb REF   git diffs
-d [DIR]              scan directory           -a / --ext / --exclude   filters
-q                    verdict only             --json                raw JSON
--judge MODEL         override judge           --debaters MODEL ...  override debaters
--budget USD          cost limit               --timeout SECONDS     per-call timeout
```

## MCP — Claude Code / Cursor

Add to `~/.claude.json` or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "verd": {
      "command": "verd-mcp",
      "env": {
        "OPENAI_API_KEY": "your-key",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1"
      }
    }
  }
}
```

Then use `verd`, `verdl`, or `verdh` as tools directly in chat. Ask a question, paste code, then say "use verd to check this."

## Slack

Install with Slack dependencies:

```bash
pip install "verd[slack]"
```

Create a Slack app with Socket Mode enabled, add bot scopes (`app_mentions:read`, `channels:history`, `groups:history`, `chat:write`, `reactions:write`, `im:history`, `im:write`, `users:read`), then:

```bash
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...
export SLACK_SIGNING_SECRET=...
verd-slack
```

Usage in Slack:
- `@verd what do you think?` — reads thread or last 20 channel messages, debates, replies in thread
- `@verd deep is this secure?` — uses verdh (5 models + web search)
- `@verd quick is this right?` — uses verdl (fast, 2 models)
- `@verd last 50 what's the consensus?` — reads last 50 messages as context
- `/verd should we use Kafka?` — slash command with live progress updates
- `/verdl is this correct?` — quick slash command
- `/verdh any security issues?` — deep slash command

Optional: restrict access via environment variables:
```bash
export VERD_ALLOWED_CHANNELS=C123,C456    # empty = all channels
export VERD_ALLOWED_USERS=U123,U456       # empty = all users
```
