import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from models import (
    Action, ActionType, Observation, Reward, StepResponse, TableSummary,
)
from tasks import TASKS


class SQLEnv:
    """OpenEnv-compliant SQL debugging environment backed by in-memory SQLite."""

    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self.current_task_id: Optional[str] = None
        self.step_count: int = 0
        self.max_steps: int = 0
        self.done: bool = False
        self.history: List[str] = []

    # ------------------------------------------------------------------ reset
    def reset(self, task_id: str = "task1") -> Observation:
        if self.conn:
            self.conn.close()

        self.current_task_id = task_id
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.step_count = 0
        self.done = False
        self.history = []

        task = TASKS[task_id]
        self.max_steps = task.max_steps
        task.setup(self.conn)

        return self._build_obs("Environment reset. Inspect the schema and solve the task.")

    # ------------------------------------------------------------------ step
    def step(self, action: Action) -> StepResponse:
        if self.done:
            return StepResponse(
                observation=self._build_obs("Episode already finished."),
                reward=Reward(value=0.0, reason="Episode finished"),
                done=True,
                info={"step": self.step_count, "max_steps": self.max_steps},
            )

        self.step_count += 1
        self.history.append(f"Step {self.step_count}: {action.action_type.value}({action.params})")

        # 1. Execute the action and get human-readable result
        result_msg = self._dispatch(action)

        # 2. Grade current DB state
        task = TASKS[self.current_task_id]
        score, reason = task.grade(self.conn)

        # Task solved — keep full 1.0 score
        if score >= 1.0:
            score = 1.0
            self.done = True
        elif self.step_count >= self.max_steps:
            self.done = True

        reward = Reward(
            value=min(score, 1.0),
            reason=reason,
            partial_credits={"progress": round(score, 3)},
        )

        return StepResponse(
            observation=self._build_obs(result_msg),
            reward=reward,
            done=self.done,
            info={"step": self.step_count, "max_steps": self.max_steps, "resolved": score >= 1.0},
        )

    # ------------------------------------------------------------------ state
    def state(self) -> Dict[str, Any]:
        return {
            "task_id": self.current_task_id,
            "step": self.step_count,
            "max_steps": self.max_steps,
            "done": self.done,
            "history": self.history,
        }

    # ------------------------------------------------- action dispatch
    def _dispatch(self, action: Action) -> str:
        at = action.action_type
        p = action.params

        if at == ActionType.execute_sql:
            return self._exec_sql(p.get("sql", ""))

        if at == ActionType.get_schema:
            return self._get_schema_text()

        if at == ActionType.get_table_info:
            tbl = p.get("table", p.get("table_name", ""))
            return self._get_table_info(tbl)

        if at == ActionType.submit:
            sql = p.get("sql", "")
            if sql:
                return self._exec_sql(sql)
            return "Submission recorded."

        return "Unknown action type."

    def _exec_sql(self, sql: str) -> str:
        if not sql.strip():
            return "Empty SQL statement."
        try:
            cursor = self.conn.execute(sql)
            # If the statement returns rows (SELECT, PRAGMA, etc.)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                # Mark easy task as solved if we got results from a valid SELECT
                if rows and self.current_task_id == "task1":
                    sql_upper = sql.upper()
                    if "SELECT" in sql_upper and "USERS" in sql_upper and "AND" in sql_upper and "ANDD" not in sql_upper:
                        self.conn._easy_solved = True
                display = rows[:10]  # limit display
                return f"Query returned {len(rows)} row(s):\n{display}"
            else:
                self.conn.commit()
                return f"Statement executed successfully. Rows affected: {cursor.rowcount}"
        except Exception as e:
            return f"SQL Error: {e}"

    def _get_schema_text(self) -> str:
        cur = self.conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cur.fetchall()
        if not tables:
            return "No tables in database."
        lines = []
        for t in tables:
            lines.append(f"Table: {t[0]}\n  DDL: {t[1]}")
        return "\n".join(lines)

    def _get_table_info(self, table: str) -> str:
        if not table:
            return "Error: provide a 'table' parameter."
        try:
            info = self.conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            if not info:
                return f"Table '{table}' not found."
            cols = [{"name": r[1], "type": r[2], "notnull": bool(r[3]), "pk": bool(r[5])} for r in info]
            cnt = self.conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            return f"Table '{table}' ({cnt} rows):\n{cols}"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------- observation builder
    def _build_obs(self, last_result: str) -> Observation:
        schema_meta = []
        try:
            cur = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for row in cur.fetchall():
                tbl = row[0]
                cnt = self.conn.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
                cols_cur = self.conn.execute(f"PRAGMA table_info('{tbl}')")
                cols = [c[1] for c in cols_cur.fetchall()]
                schema_meta.append(TableSummary(table_name=tbl, columns=cols, row_count=cnt))
        except Exception:
            pass

        task = TASKS[self.current_task_id]
        broken = task.get_broken_query() if not getattr(self.conn, "_easy_solved", False) else None

        return Observation(
            schema_metadata=schema_meta,
            last_action_result=last_result,
            task_description=(
                f"Task: {task.name} ({task.difficulty})\n"
                f"Description: {task.description}\n"
                f"Objective: {task.objective}"
            ),
            broken_query=broken,
        )

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
