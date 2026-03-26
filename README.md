# verd

**Five minds enter. They argue, challenge, cross-examine. Only the truth walks out.**

verd spawns multiple AI models from different families — each with a specialized role, has them debate your question across rounds, then a stronger judge delivers the final verdict with strengths, issues, and actionable fixes.

Use it everywhere: **CLI** for code reviews, **MCP** inside Claude Code and Cursor, and **Slack** as `@verd` in any conversation.
## Getting Started

**Requires Python 3.11+.**

```bash
pip install verd
python3 -m verd setup
```

The setup wizard walks you through provider selection (OpenRouter, LiteLLM, or other) and outputs the exact config you need — for both CLI (`.env`) and MCP (JSON to paste into your editor config).

verd runs multiple models in parallel (Claude, Gemini, GPT, DeepSeek) so it needs a multi-provider router. [OpenRouter](https://openrouter.ai) is the easiest — one key, all models. [LiteLLM proxy](https://docs.litellm.ai/) works too.

## Usage

```bash
verd "Kafka or RabbitMQ for our event pipeline?" -f architecture.md
verd "can this auth middleware be bypassed?" -f auth.py middleware.py
verdh "should we merge this?" -gb main
verdl "is O(n^2) acceptable for n=1000?"
verd "any issues?" -d                          # scan current directory
verd "any issues?" -d ./src -a                 # scan all files, skip smart selection
verd "is this correct?" -c "SELECT * FROM users WHERE id=$id"
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
| `verdl` | 2 + judge | analyst, devils_advocate | 1 | ~15s+ | ~$0.01 |
| `verd` | 4 + judge | analyst, devils_advocate, logic_checker, pragmatist | 2 | ~30s+ | ~$0.05+ |
| `verdh` | 5 + judge + web | analyst, devils_advocate, logic_checker, fact_checker, pragmatist | 3 | ~60s+ | ~$0.25+ |

## Benchmark

Tested on the [Martian Code Review Benchmark](https://codereview.withmartian.com) — 50 real PRs from Cal.com, Discourse, Grafana, Keycloak, and Sentry with expert-labeled golden comments. No code-review-specific tuning.

| Mode | Precision | Recall | F1 Score | Avg Issues |
|------|-----------|--------|----------|------------|
| GPT-5.4 (alone) | 13.0% | 70.6% | 21.9% | 14.6 |
| Claude Opus 4.6 (alone) | 18.5% | 69.9% | 29.2% | 10.1 |
| **verdh (5-model debate)** | **29.1%** | **64.0%** | **40.0%** | **5.9** |

**+37% F1 over Claude solo. 57% more precise. 42% fewer false positives.** 

## How it works

1. Your question + content gets sent to multiple AI models in parallel
2. Each model has a **specialized role** (analyst, devils_advocate, logic_checker, fact_checker, pragmatist)
3. Models see each other's responses and cross-examine for 1-3 rounds
4. **Anti-groupthink prompts** ensure models hold their ground when they have evidence — consensus without new evidence is rejected
5. A stronger judge model synthesizes the debate, weighting each reviewer by their role
6. **Confidence is calculated from vote distribution** — a fact_checker's dissent lowers confidence more than a devils_advocate's expected pushback
7. You get: verdict, vote breakdown, strengths, issues, unique catches, dissent, and actionable fixes

The key insight: different model families have different blind spots and training biases. Claude spots nuance GPT misses. Gemini catches logic errors DeepSeek overlooks. More importantly — if the same model writes the review and judges its quality, it's likely to agree with itself. Cross-model diversity means the judge is a genuine quality gate, not a model grading its own homework. The debate surfaces what each model uniquely caught and tells you exactly which model caught what.

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

Override models via env vars or CLI flags. Per-tier env vars let you set different models for each mode:

```bash
VERDL_JUDGE=o4-mini            VERDL_DEBATERS=gpt-4.1-mini,gemini-3.1-flash-lite-preview
VERD_JUDGE=o3                  VERD_DEBATERS=claude-sonnet-4-6,gpt-4.1,gemini-3.1-pro-preview,gpt-4.1-mini
VERDH_JUDGE=o3                 VERDH_DEBATERS=claude-opus-4-6,deepseek-r1,gemini-3.1-pro-preview,sonar-pro,gpt-4.1
```

Or use `VERD_JUDGE` / `VERD_DEBATERS` as a global override for all tiers. `python3 -m verd setup` generates the right config for your provider.

## Flags

```
-c TEXT               inline content string
-f FILE [FILE ...]    one or more files to evaluate
-d [DIR]              read all files in a directory (default: current dir)
-g                    use unstaged git diff as content
-gs                   use staged git diff as content
-gb REF               use git diff REF...HEAD as content (e.g. main)
-a / --all            scan all files, skip smart selection (use with -d)
--ext EXT [EXT ...]   filter by extension (use with -d)
--exclude PATTERN     glob patterns to exclude (use with -d)
-q / --quiet          hide debate transcript, show only verdict
--json                output raw JSON
--judge MODEL         override judge model
--debaters MODEL ...  override debater models
--budget USD          max cost in USD — abort if estimate exceeds budget
--timeout SECONDS     override timeout per model call
--version             show version and exit
```

## MCP — Claude Code / Cursor

```bash
python3 -m verd setup    # select "MCP" and your provider
```

This prints the exact JSON to paste into `~/.claude/settings.json` (Claude Code) or `~/.cursor/mcp.json` (Cursor), with the correct absolute path to `verd-mcp` and model overrides for your provider. Then use `verd`, `verdl`, or `verdh` as tools directly in chat.

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
