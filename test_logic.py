"""Local test — verifies all 3 tasks work end-to-end without any external API."""

from logic import SQLEnv
from models import Action, ActionType


def test_easy():
    print("=== Task 1: Syntax Debugger (easy) ===")
    env = SQLEnv()
    obs = env.reset("task1")
    print(f"  Broken query: {obs.broken_query}")

    # Fix the query
    resp = env.step(Action(
        action_type=ActionType.execute_sql,
        params={"sql": "SELECT * FROM users WHERE name = 'John Doe' AND email = 'john@example.com'"}
    ))
    print(f"  Step 1 — reward={resp.reward.value:.2f}  done={resp.done}  reason={resp.reward.reason}")
    assert resp.reward.value >= 0.5, f"Expected ≥0.5, got {resp.reward.value}"
    assert resp.done, "Should be done"
    print("  ✓ PASSED\n")


def test_medium():
    print("=== Task 2: Performance Tuner (medium) ===")
    env = SQLEnv()
    obs = env.reset("task2")

    # Explore first
    resp = env.step(Action(action_type=ActionType.get_schema, params={}))
    print(f"  Step 1 (schema) — reward={resp.reward.value:.2f}")

    # Add index
    resp = env.step(Action(
        action_type=ActionType.execute_sql,
        params={"sql": "CREATE INDEX idx_orders_customer ON orders(customer_id)"}
    ))
    print(f"  Step 2 (index)  — reward={resp.reward.value:.2f}  done={resp.done}  reason={resp.reward.reason}")
    assert resp.reward.value >= 0.5, f"Expected ≥0.5, got {resp.reward.value}"
    assert resp.done, "Should be done"
    print("  ✓ PASSED\n")


def test_hard():
    print("=== Task 3: Schema Architect (hard) ===")
    env = SQLEnv()
    obs = env.reset("task3")

    steps = [
        "CREATE TABLE managers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT)",
        "INSERT INTO managers (name, email) SELECT DISTINCT manager_name, manager_email FROM projects",
        "CREATE TABLE projects_new (id INTEGER PRIMARY KEY, project_name TEXT, manager_id INTEGER REFERENCES managers(id))",
        "INSERT INTO projects_new (project_name, manager_id) SELECT p.project_name, m.id FROM projects p JOIN managers m ON p.manager_name = m.name",
        "DROP TABLE projects",
        "ALTER TABLE projects_new RENAME TO projects",
    ]
    for i, sql in enumerate(steps, 1):
        resp = env.step(Action(action_type=ActionType.execute_sql, params={"sql": sql}))
        print(f"  Step {i} — reward={resp.reward.value:.2f}  done={resp.done}")
        if resp.done:
            break

    print(f"  Final reason: {resp.reward.reason}")
    assert resp.reward.value >= 0.5, f"Expected ≥0.5, got {resp.reward.value}"
    assert resp.done, "Should be done"
    print("  ✓ PASSED\n")


if __name__ == "__main__":
    test_easy()
    test_medium()
    test_hard()
    print("All 3 tasks PASSED ✓")
