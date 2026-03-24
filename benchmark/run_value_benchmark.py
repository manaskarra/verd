"""Value benchmark: tests that prove verd's 3 value propositions.

Test 1: DECISIVENESS — subjective questions, compare confidence + recommendation clarity
Test 2: BLIND SPOTS — cases where one model is confidently wrong, debate catches it
Test 3: UNIQUE CATCHES — count issues found by debate that single model misses

Baselines: claude-sonnet-4-6 alone AND gpt-5.4 alone (two single models)
Debate: verd (4 models, 2 rounds)
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from verd.engine import run_debate
from verd.config import get_client, estimate_cost

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BASELINES = ["claude-sonnet-4-6", "gpt-5.4"]


# ============================================================
# SINGLE MODEL RUNNER
# ============================================================

async def run_single(model: str, content: str, claim: str) -> dict:
    start = time.time()
    prompt = f"{claim}"
    if content:
        prompt = f"{claim}\n\n```\n{content}\n```"
    prompt += (
        "\n\nGive your expert analysis. Be specific, list concrete issues and recommendations.\n"
        "End with: VERDICT: PASS/FAIL/UNCERTAIN and confidence 0.0-1.0"
    )
    try:
        response = await asyncio.wait_for(
            get_client().chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=4096,
            ), timeout=120)
        text = response.choices[0].message.content or ""
        usage = response.usage
        elapsed = round(time.time() - start, 1)
        cost = estimate_cost(model, usage.prompt_tokens, usage.completion_tokens)

        m = re.search(r'VERDICT:\s*(PASS|FAIL|UNCERTAIN)\s*([\d.]+)?', text, re.IGNORECASE)
        if m:
            verdict, conf = m.group(1).upper(), float(m.group(2) or 0.5)
        else:
            verdict = "UNCERTAIN"
            conf = 0.5

        issues = re.findall(r'(?:^|\n)\s*[-•*\d.]+[.)]\s+(.+)', text, re.MULTILINE)

        return {"verdict": verdict, "confidence": conf, "elapsed": elapsed,
                "cost": round(cost, 4), "issues_found": len(issues),
                "response": text[:1000], "model": model}
    except Exception as e:
        return {"verdict": "UNCERTAIN", "confidence": 0, "elapsed": round(time.time()-start, 1),
                "cost": 0, "issues_found": 0, "response": str(e)[:200], "model": model}


# ============================================================
# TEST 1: DECISIVENESS
# ============================================================

DECISIVENESS_TESTS = [
    {"name": "Kafka vs RabbitMQ", "claim": "Should we use Kafka or RabbitMQ for our event-driven microservices? We have 50 services, 10K events/sec, need ordering guarantees, and our team knows RabbitMQ but not Kafka.", "code": ""},
    {"name": "Monolith vs microservices", "claim": "We're a 5-person startup building a fintech app. Should we start with microservices or a monolith?", "code": ""},
    {"name": "ORM vs raw SQL", "claim": "Should we use the ORM or raw SQL for analytics queries joining 6 tables with 100M rows?", "code": ""},
    {"name": "bcrypt vs argon2 migration", "claim": "We use bcrypt with 12 rounds for 500K users. Should we migrate to argon2id? No breaches, just proactive.", "code": ""},
    {"name": "REST vs gRPC vs events", "claim": "3 services need to communicate: OrderService, PaymentService, NotificationService. Orders need payment confirmation before completing. Should we use REST, gRPC, or async events?", "code": ""},
    {"name": "Redis vs PostgreSQL for caching", "claim": "Should we add Redis as a cache layer or just optimize our PostgreSQL queries? We have 1000 req/sec, 50ms avg response time, 8GB RAM on the DB server.", "code": ""},
    {"name": "TypeScript strict mode", "claim": "Should we enable TypeScript strict mode on a 200K line legacy codebase? It would require fixing ~3000 type errors but our team keeps shipping type-related bugs.", "code": ""},
    {"name": "Feature flags build vs buy", "claim": "Should we build our own feature flag system or use LaunchDarkly? We have 20 engineers, 50 flags, and need percentage rollouts.", "code": ""},
]


# ============================================================
# TEST 2: BLIND SPOTS
# ============================================================

BLINDSPOT_TESTS = [
    {
        "name": "Subtle TOCTOU race condition",
        "claim": "Is this file operation safe?",
        "code": '''import os
def safe_write(filepath, data):
    """Safely write data to file, creating dirs if needed."""
    dir_path = os.path.dirname(filepath)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            f.write(data)
        return True
    return False''',
        "expected": "FAIL",
        "why": "TOCTOU: exists check then makedirs/open is raceable. Also no atomic write.",
    },
    {
        "name": "Integer overflow in pagination",
        "claim": "Is this pagination correct?",
        "code": '''def paginate(items, page=1, per_page=20):
    total = len(items)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "data": items[start:end],
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }''',
        "expected": "FAIL",
        "why": "No validation: page=0 gives negative index, page=-1 wraps around, per_page=0 divides by zero.",
    },
    {
        "name": "Regex DoS (ReDoS)",
        "claim": "Is this email validation safe for a web API?",
        "code": '''import re
EMAIL_REGEX = re.compile(r'^([a-zA-Z0-9_.+-]+)+@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$')
def validate_email(email):
    if len(email) > 254:
        return False
    return bool(EMAIL_REGEX.match(email))''',
        "expected": "FAIL",
        "why": "Nested quantifiers ()+@ make this ReDoS vulnerable. Crafted input causes exponential backtracking.",
    },
    {
        "name": "Timezone-naive datetime comparison",
        "claim": "Is this session expiry check correct?",
        "code": '''from datetime import datetime, timedelta
def is_session_valid(session):
    created_at = session["created_at"]  # stored as UTC datetime
    max_age = timedelta(hours=24)
    return datetime.now() - created_at < max_age''',
        "expected": "FAIL",
        "why": "datetime.now() is local time, created_at is UTC. In any timezone != UTC, sessions expire wrong.",
    },
    {
        "name": "Mutable default argument",
        "claim": "Is this function correct?",
        "code": '''def add_item(item, items=[]):
    items.append(item)
    return items

def create_config(overrides={}):
    config = {"debug": False, "log_level": "INFO"}
    config.update(overrides)
    return config''',
        "expected": "FAIL",
        "why": "Classic Python gotcha: mutable default args shared across calls.",
    },
    {
        "name": "Unchecked None propagation",
        "claim": "Is this data processing pipeline robust?",
        "code": '''def process_user(raw_data):
    user = parse_user(raw_data)
    profile = user.get("profile")
    address = profile.get("address")
    city = address.get("city", "Unknown")
    return {"user_id": user["id"], "city": city}''',
        "expected": "FAIL",
        "why": "If profile is None, profile.get() throws AttributeError. Cascading None not handled.",
    },
    {
        "name": "Hash comparison timing attack",
        "claim": "Is this API key verification secure?",
        "code": '''import hashlib
def verify_api_key(provided_key, stored_hash):
    provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
    return provided_hash == stored_hash''',
        "expected": "FAIL",
        "why": "String == comparison is not constant-time, enabling timing side-channel attack.",
    },
    {
        "name": "Silent data truncation",
        "claim": "Is this data storage correct?",
        "code": '''def store_user_bio(user_id, bio_text):
    # bio column is VARCHAR(500) in the database
    db.execute(
        "UPDATE users SET bio = %s WHERE id = %s",
        (bio_text, user_id)
    )
    return {"success": True, "bio": bio_text}''',
        "expected": "FAIL",
        "why": "Returns full bio_text but DB silently truncates to 500 chars. Response doesn't match stored data.",
    },
]


# ============================================================
# RUNNER
# ============================================================

async def run_test_suite(name: str, tests: list[dict], test_type: str) -> list[dict]:
    print(f"\n{'='*60}")
    print(f"{name} ({len(tests)} cases)")
    print("="*60)

    results = []
    for i, test in enumerate(tests, 1):
        t_name = test["name"]
        claim = test["claim"]
        code = test.get("code", "").strip()
        expected = test.get("expected")

        print(f"\n  [{i}/{len(tests)}] {t_name}")

        r = {"name": t_name, "test_type": test_type}
        if expected:
            r["expected"] = expected

        # Baselines
        for model in BASELINES:
            short = model.split("-")[0]
            print(f"    {short:8s}...", end="", flush=True)
            sr = await run_single(model, code, claim)
            if expected:
                sr["correct"] = sr["verdict"] == expected
            r[model] = sr
            c = f" {'✓' if sr.get('correct') else '✗'}" if expected else ""
            print(f" {sr['verdict']} {sr['confidence']:.0%}{c}"
                  f" | {sr['issues_found']} issues | {sr['elapsed']}s ${sr['cost']:.3f}")

        # verd
        content = f"```python\n{code}\n```" if code else ""
        print(f"    {'verd':8s}...", end="", flush=True)
        try:
            vr = await run_debate(content, claim, "verd")
            vr_summary = {
                "verdict": vr.get("verdict"), "confidence": vr.get("confidence", 0),
                "elapsed": vr.get("elapsed", 0), "cost": vr.get("cost", 0),
                "issues_found": len(vr.get("issues", [])),
                "unique_catches": vr.get("unique_catches", []),
                "consensus": vr.get("consensus"),
                "model_votes": vr.get("model_votes", {}),
                "headline": (vr.get("headline") or "")[:200],
                "dissent": (vr.get("dissent") or "")[:200],
            }
            if expected:
                vr_summary["correct"] = vr.get("verdict") == expected
        except Exception as e:
            vr_summary = {"verdict": "ERROR", "confidence": 0, "elapsed": 0,
                          "cost": 0, "issues_found": 0, "headline": str(e)[:100]}
            if expected:
                vr_summary["correct"] = False
        r["verd"] = vr_summary
        c = f" {'✓' if vr_summary.get('correct') else '✗'}" if expected else ""
        print(f" {vr_summary['verdict']} {vr_summary['confidence']:.0%}{c}"
              f" | {vr_summary.get('issues_found', 0)} issues"
              f" | {vr_summary.get('consensus', '?')}"
              f" | {vr_summary['elapsed']}s ${vr_summary['cost']:.3f}")

        results.append(r)

        # Save incrementally
        with open(RESULTS_DIR / "value_benchmark.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

    return results


def print_summary(name: str, results: list[dict], modes: list[str]):
    n = len(results)
    if not n:
        return
    print(f"\n--- {name} ({n} cases) ---")
    header = f"{'Mode':>12} |"
    if any(r.get(modes[0], {}).get("correct") is not None for r in results):
        header += f" {'Correct':>10} |"
    header += f" {'Avg Conf':>8} | {'Avg Issues':>10} | {'Cost':>8} | {'Time':>6}"
    print(header)
    print("-" * len(header))

    for mode in modes:
        valid = [r for r in results if mode in r]
        if not valid:
            continue
        avg_conf = sum(r[mode].get("confidence", 0) for r in valid) / len(valid)
        avg_issues = sum(r[mode].get("issues_found", 0) for r in valid) / len(valid)
        total_cost = sum(r[mode].get("cost", 0) for r in valid)
        total_time = sum(r[mode].get("elapsed", 0) for r in valid)

        line = f"{mode:>12} |"
        if any(r.get(mode, {}).get("correct") is not None for r in valid):
            correct = sum(1 for r in valid if r[mode].get("correct"))
            line += f" {correct}/{len(valid)} ({correct/len(valid)*100:3.0f}%) |"
        line += (f" {avg_conf:>7.0%} | {avg_issues:>10.1f} | ${total_cost:>7.2f} | {total_time:>5.0f}s")
        print(line)


async def main():
    print("=" * 60)
    print("VERD VALUE BENCHMARK")
    print("Proving the 3 value props: decisiveness, blind spots, unique catches")
    print(f"Baselines: {', '.join(BASELINES)} | Debate: verd")
    print("=" * 60)

    all_results = {}

    # Test 1: Decisiveness (first 5)
    dec_results = await run_test_suite(
        "TEST 1: DECISIVENESS — subjective questions",
        DECISIVENESS_TESTS[:5], "decisiveness")
    all_results["decisiveness"] = dec_results

    # Test 2: Blind spots (first 5)
    blind_results = await run_test_suite(
        "TEST 2: BLIND SPOTS — subtle bugs single models miss",
        BLINDSPOT_TESTS[:5], "blindspot")
    all_results["blindspots"] = blind_results

    # Save
    with open(RESULTS_DIR / "value_benchmark.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    modes = BASELINES + ["verd"]

    print_summary("DECISIVENESS (no right answer — higher confidence = better)",
                   dec_results, modes)

    print_summary("BLIND SPOTS (expected FAIL — accuracy matters)",
                   blind_results, modes)

    # Unique catches analysis
    print("\n--- UNIQUE CATCHES (what verd found that single models missed) ---")
    total_catches = 0
    for r in blind_results:
        catches = r.get("verd", {}).get("unique_catches", [])
        if catches:
            print(f"  {r['name']}:")
            for c in catches:
                print(f"    ! {c}")
                total_catches += 1
    print(f"\n  Total unique catches across {len(blind_results)} tests: {total_catches}")

    print(f"\nResults: {RESULTS_DIR / 'value_benchmark.json'}")


if __name__ == "__main__":
    asyncio.run(main())
