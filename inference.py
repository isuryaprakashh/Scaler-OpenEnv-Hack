"""
inference.py — SQL Database Debugger Agent baseline inference script.

Mandatory env vars (per hackathon spec):
    API_BASE_URL   LLM endpoint   (default: https://router.huggingface.co/v1)
    MODEL_NAME     Model id       (default: Qwen/Qwen2.5-72B-Instruct)
    HF_TOKEN       API key

Usage:
    python inference.py                    # runs ALL 3 tasks
    SQL_ENV_TASK=task2 python inference.py  # runs only task2
"""

import json
import os
import sys
import textwrap
from typing import List, Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")

ALL_TASKS = ["task1", "task2", "task3"]
SINGLE_TASK = os.getenv("SQL_ENV_TASK", "")  # empty → run all
BENCHMARK = "sql-debugger-agent"
MAX_STEPS = 10
TEMPERATURE = 0.2

# ── Logging helpers (mandatory format) ────────────────────────────────
def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} "
        f"done={str(done).lower()} error={error or 'null'}",
        flush=True,
    )

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rstr = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.2f} rewards={rstr}",
        flush=True,
    )

# ── Agent prompt ──────────────────────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""\
You are a SQL Expert and Database Debugger agent.
You interact with a SQLite environment through JSON actions.

Available actions (respond with ONLY a JSON object, nothing else):

  {"action_type": "get_schema", "params": {}}
  {"action_type": "get_table_info", "params": {"table": "<name>"}}
  {"action_type": "execute_sql", "params": {"sql": "<SQL statement>"}}
  {"action_type": "submit", "params": {"sql": "<final fix SQL>"}}

Strategy:
1. First inspect the schema and tables.
2. Understand the problem described in the task.
3. Execute exploratory queries if needed.
4. Apply the fix using execute_sql or submit.

Rules:
- Output ONLY a single JSON object per turn. No markdown, no explanation.
- For the easy task, fix the broken query shown in the observation.
- For the medium task, add an index to optimize performance.
- For the hard task, normalize the schema by creating new tables and migrating data.
""")


def parse_action(raw: str) -> Optional[dict]:
    """Extract JSON from model output, handling markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s:e])
            except json.JSONDecodeError:
                pass
    return None


# ── Run one task ──────────────────────────────────────────────────────
def run_task(client: OpenAI, task_id: str) -> float:
    """Run a single task against the environment. Returns the final score."""
    rewards: List[float] = []
    steps_taken = 0
    success = False
    score = 0.0

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        # Reset
        r = requests.post(f"{ENV_URL}/reset", json={"task_id": task_id}, timeout=30)
        r.raise_for_status()
        obs = r.json()

        history = []

        for step in range(1, MAX_STEPS + 1):
            # Build user message from observation
            user_msg = json.dumps(obs, indent=2)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history[-8:],  # keep last 4 turns
                {"role": "user", "content": user_msg},
            ]

            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=512,
            )

            raw = (completion.choices[0].message.content or "").strip()
            action_dict = parse_action(raw)

            if action_dict is None:
                log_step(step, raw[:80], 0.0, False, "Failed to parse action")
                history.append({"role": "assistant", "content": raw})
                history.append({"role": "user", "content": "Invalid JSON. Try again with only a JSON object."})
                rewards.append(0.0)
                steps_taken = step
                continue

            # Step env
            sr = requests.post(f"{ENV_URL}/step", json=action_dict, timeout=30)
            sr.raise_for_status()
            data = sr.json()

            obs = data["observation"]
            reward = data["reward"]["value"]
            done = data["done"]
            error = data["observation"].get("error_message")

            rewards.append(reward)
            steps_taken = step

            action_str = json.dumps(action_dict)
            log_step(step, action_str, reward, done, error)

            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content": f"Result: {obs.get('last_action_result', '')}"})

            if done:
                break

        score = rewards[-1] if rewards else 0.01
        score = min(max(score, 0.01), 0.99)
        success = score >= 0.5

    except Exception as exc:
        print(f"[DEBUG] Error in {task_id}: {exc}", file=sys.stderr)

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return score


# ── Main ──────────────────────────────────────────────────────────────
def main() -> None:
    if not HF_TOKEN:
        print("[ERROR] HF_TOKEN is not set. Export it or add to .env", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    # Determine which tasks to run
    tasks = [SINGLE_TASK] if SINGLE_TASK else ALL_TASKS

    scores = {}
    for task_id in tasks:
        scores[task_id] = run_task(client, task_id)

    # Summary
    print("[DEBUG] " + "=" * 50, flush=True)
    print("[DEBUG] BASELINE RESULTS SUMMARY", flush=True)
    print("[DEBUG] " + "=" * 50, flush=True)
    for tid, sc in scores.items():
        status = "✓ PASS" if sc >= 0.5 else "✗ FAIL"
        print(f"[DEBUG]   {tid}: score={sc:.2f}  {status}", flush=True)
    avg = sum(scores.values()) / len(scores) if scores else 0.0
    print(f"[DEBUG]   Average: {avg:.2f}", flush=True)
    print("[DEBUG] " + "=" * 50, flush=True)


if __name__ == "__main__":
    main()
