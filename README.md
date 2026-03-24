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

Edit `verd/models.py` to customize which models debate and their roles.

## Usage

```bash
# Architecture decisions
verd "Kafka or RabbitMQ for our event pipeline?" -f architecture.md

# Security review
verd "can this auth middleware be bypassed?" -f auth.py middleware.py routes.py

# Payment logic
verd "is this payment flow handling refunds correctly?" -d payments/ --ext .py

# Full codebase audit
verdh "full security audit" -d . -a

# Quick sanity check
verdl "is O(n^2) acceptable for n=1000?"

# Pre-merge review
verdh "should we merge this?" -gb main

# Git diffs
verd "do these changes break backwards compatibility?" -g     # unstaged
verd "any correctness issues before I ship?" -gs               # staged

# Pipe anything
cat deploy.yaml | verd "any misconfigs that could expose prod?"

# Quiet mode (verdict only, no transcript)
verd "is this rate limiter safe under concurrency?" -f rate_limiter.py -q

# JSON output
verd "is this rate limiter safe under concurrency?" -f rate_limiter.py --json
```

In Slack:
```
@verd should we migrate to gRPC or stick with REST?
@verd deep is this thread's auth proposal secure?
@verd quick is this regex correct?
/verd should we use Kafka?
```

## When to use verd

**The second opinion you run before you ship.**

- **"Should we?" decisions** — Ask one model "Kafka or RabbitMQ?" and get one opinion at 50% confidence. Ask verd and get 4-5 perspectives that challenge each other, a clear recommendation, and dissent noted. A single model never tells you when it's wrong.

- **High-stakes code** — Security reviews, auth flows, payment logic. Not because verd finds more bugs — but because it catches the 5% of cases where any single model would be confidently wrong. If sonnet says "this JWT code looks fine" and it has `verify_signature: False`, verd's debate catches it.

- **Defensible decisions** — "I ran this through 5 AI models and they debated for 3 rounds. 4 agreed, 1 dissented on X. Here's the full transcript." That's more defensible than "Claude said it's fine."

Like a code review from 5 senior engineers that costs $0.05-$0.30. You don't use it on every line — you use it on the 3 things that matter.

**Don't use verd for** simple factual questions, writing code, or anything where speed matters more than thoroughness.

## How it works

1. Your question + content gets sent to multiple AI models in parallel
2. Each model has a **specialized role** (analyst, devils_advocate, logic_checker, fact_checker, pragmatist)
3. Models see each other's responses and cross-examine for 1-3 rounds
4. **Anti-groupthink prompts** ensure models hold their ground when they have evidence — consensus without new evidence is rejected
5. A stronger judge model synthesizes the debate, weighting each reviewer by their role
6. **Confidence is calculated from vote distribution** — a fact_checker's dissent lowers confidence more than a devils_advocate's expected pushback
7. You get: verdict, vote breakdown, strengths, issues, unique catches, dissent, and actionable fixes

The key insight: different models have different blind spots. Claude spots nuance GPT misses. Gemini catches logic errors DeepSeek overlooks. The debate surfaces all of them — and tells you exactly which model caught what.

## Output

verd shows what makes multi-model debate valuable:

```
FAIL  77%  In-memory rate limiter is unsafe for production

claude:FAIL  gpt:FAIL  gemini:FAIL  gpt:FAIL  (FULL)

+ Conceptually correct sliding-window logic
+ Old timestamps pruned on every call

- Global dict is unsynchronized — race conditions in multi-thread servers
- State resets on restart, multiplied across horizontally scaled instances
- Per-user lists grow without bounds — memory leak / DoS vector

! gpt-5-mini caught the risk of system clock jumps with time.time()
! gpt-4.1 highlighted the O(N) per-request performance cost

→ Move state to Redis with atomic operations
→ Use time.monotonic() for interval calculations
→ Add TTL/eviction for inactive user keys

completed in 69.3s • 22,449 tokens • ~$0.07
```

- **Vote breakdown** — who voted what, at a glance
- **Unique catches** (`!`) — what each model uniquely spotted that others missed
- **Dissent** — who disagreed, what they argued, and why it matters
- **Confidence** — calculated from vote distribution weighted by role, not judge vibes

## Modes

| Command | Debaters | Roles | Rounds | Speed | Cost |
|---------|----------|-------|--------|-------|------|
| `verdl` | 2 + judge | analyst, devils_advocate | 1 | ~10s | ~$0.01 |
| `verd` | 4 + judge | analyst, devils_advocate, logic_checker, pragmatist | 2 | ~30s | ~$0.15+ |
| `verdh` | 5 + judge + web | analyst, devils_advocate, logic_checker, fact_checker, pragmatist | 3 | ~70s | ~$0.40+ |

## Roles

Each model in the debate gets a specialized role:

| Role | Job | Example catch |
|------|-----|---------------|
| **analyst** | Balanced initial assessment, main arguments for and against | "The architecture is sound but the auth flow has a gap" |
| **devils_advocate** | Find what others miss — edge cases, hidden assumptions, failure modes | "What happens when the token expires mid-transaction?" |
| **logic_checker** | Verify reasoning quality — fallacies, off-by-one, race conditions | "The pagination math is wrong: total_pages needs ceil division" |
| **fact_checker** | Web-grounded verification — do these APIs/libraries actually work? | "That library was deprecated in v3, use the new API" |
| **pragmatist** | Real-world practicality — will this ship? What's the ops burden? | "This works but needs 3 new infra dependencies your team doesn't know" |

The judge weighs each reviewer's input by role — a fact_checker citing sources carries more weight than a devils_advocate pushing back.

## Flags

```
claim                     the question to evaluate (required)

Content input (pick one, or auto-scans current dir):
  -c, --context TEXT      inline content string
  -f FILE [FILE ...]      one or more files
  -d [DIR]                directory (default: current dir)
  -g, --git               unstaged git diff
  -gs, --git-staged       staged git diff
  -gb, --git-branch REF   git diff REF...HEAD

Directory filters (use with -d):
  -a, --all               scan all files, skip smart selection
  --ext EXT [EXT ...]     filter by extension (.py .ts)
  --exclude PAT [PAT ...] glob patterns to exclude (test_*)

Output:
  -q, --quiet             hide debate transcript, show only verdict
  --json                  raw JSON output
  --timeout SECONDS       override timeout per model call
  --version               show version
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
