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

from dotenv import load_dotenv
from openai import OpenAI

# Direct environmental imports - bypasses HTTP for better reliability in eval
from server.logic import SQLEnv
from server.models import Action, ActionType

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────
# Defaults as required by guidelines
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    print("[ERROR] HF_TOKEN is not set. Environment variable is mandatory.", file=sys.stderr)
    sys.exit(1)

ALL_TASKS = ["task1", "task2", "task3"]
SINGLE_TASK = os.getenv("SQL_ENV_TASK", "")  # empty → run all
BENCHMARK = "sql-debugger-agent"
MAX_STEPS = 10
TEMPERATURE = 0.2

# ── Logging helpers (STRICT MANDATORY FORMAT) ─────────────────────────
def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    # Error must be 'null' if none
    err_str = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} "
        f"done={str(done).lower()} error={err_str}",
        flush=True,
    )

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    # Format: [END] success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
    rstr = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rstr}",
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
def run_task(client: OpenAI, env: SQLEnv, task_id: str) -> float:
    """Run a single task against the environment. Returns the final reward."""
    rewards: List[float] = []
    steps_taken = 0
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        # Reset environment
        obs_obj = env.reset(task_id)
        obs = obs_obj.model_dump()

        history = []

        for step in range(1, MAX_STEPS + 1):
            # Build user message from observation
            user_msg = json.dumps(obs, indent=2)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history[-8:],  # maintain context
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
                log_step(step, "parse_error", 0.05, False, "Failed to parse action")
                history.append({"role": "assistant", "content": raw})
                history.append({"role": "user", "content": "Invalid JSON. Try again with only a JSON object."})
                rewards.append(0.05)
                steps_taken = step
                continue

            # Step env directly
            try:
                # Validate action dict into Pydantic model
                action_obj = Action(**action_dict)
                resp = env.step(action_obj)
                
                obs = resp.observation.model_dump()
                reward = min(max(resp.reward.value, 0.05), 0.95)
                done = resp.done
                error = resp.observation.error_message

                rewards.append(reward)
                steps_taken = step

                # Clean action string for logging
                action_str = f"{action_obj.action_type.value}({json.dumps(action_obj.params)})"
                log_step(step, action_str, reward, done, error)

                history.append({"role": "assistant", "content": raw})
                history.append({"role": "user", "content": f"Result: {obs.get('last_action_result', '')}"})

                if done:
                    success = reward >= 0.5
                    break
            except Exception as e:
                log_step(step, "runtime_error", 0.05, False, str(e))
                rewards.append(0.05)
                steps_taken = step
                break

    except Exception as exc:
        print(f"[DEBUG] Error in {task_id}: {exc}", file=sys.stderr)
    finally:
        # Guarantee at least one reward so [END] line is never empty
        if not rewards:
            rewards.append(0.05)
        # Final safety clamp for the rewards list
        clamped_rewards = [min(max(r, 0.05), 0.95) for r in rewards]
        final_score = clamped_rewards[-1] if clamped_rewards else 0.05
        log_end(success=success, steps=steps_taken, score=final_score, rewards=clamped_rewards)

    return clamped_rewards[-1] if clamped_rewards else 0.05


# ── Main ──────────────────────────────────────────────────────────────
def main() -> None:
    # Initialize OpenAI client
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    
    # Initialize Environment
    env = SQLEnv()

    # Determine which task to run (ONLY ONE TASK PER EXECUTION)
    # Default to task1 if not specified
    task_id = SINGLE_TASK if SINGLE_TASK else "task1"

    run_task(client, env, task_id)
        
    env.close()

if __name__ == "__main__":
    main()
