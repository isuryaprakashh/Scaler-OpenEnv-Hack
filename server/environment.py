import sqlite3
import os
from typing import Any, Dict, List, Optional, Tuple

from models import (
    Action, ActionType, Observation, Reward, StepResponse, TableSummary,
)
from .tasks import TASKS


class SQLEnv:
    """OpenEnv-compliant SQL debugging environment backed by in-memory SQLite."""

    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self.current_task_id: Optional[str] = None
        self.step_count: int = 0
        self.max_steps: int = 0
        self.done: bool = False
        self.history: List[str] = []

    def reset(self, task_id: str) -> Observation:
        """Reset environment to a specific task."""
        if task_id not in TASKS:
            task_id = "task-0"

        self.current_task_id = task_id
        task = TASKS[task_id]
        self.max_steps = task.max_steps
        self.step_count = 0
        self.done = False
        self.history = []

        # Fresh in-memory DB for each reset
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        task.setup(self.conn)

        msg = f"Environment reset to {task.name}. {task.objective}"
        return self._build_obs(msg)

    def step(self, action: Action) -> StepResponse:
        """Perform one environment step."""
        if self.done:
            # Already finished, just return current state
            score, reason = TASKS[self.current_task_id].grade(self.conn)
            return self._build_step_response(0.001, reason, "Environment already done.")

        self.step_count += 1
        self.history.append(f"Step {self.step_count}: {action.action_type.value}({action.params})")

        # 1. Execute the action and get human-readable result
        result_msg = self._dispatch(action)

        # 2. Grade current DB state
        task = TASKS[self.current_task_id]
        score, reason = task.grade(self.conn)

        # Task solved — keep full 0.95 score
        if score >= 0.95:
            score = 0.95
            self.done = True
        elif self.step_count >= self.max_steps:
            self.done = True

        # Strictly clamp scores to (0.05, 0.95) for evaluators
        safe_score = min(max(score, 0.05), 0.95)

        reward = Reward(
            value=safe_score,
            reason=reason,
            partial_credits={"progress": round(safe_score, 3)},
        )

        return StepResponse(
            observation=self._build_obs(result_msg),
            reward=reward,
            done=self.done,
            info={"step": self.step_count, "max_steps": self.max_steps, "resolved": score >= 0.95},
        )

    # ------------------------------------------------------------------ state
    def get_state(self) -> Observation:
        """Returns current state as an Observation object."""
        return self._build_obs("Current state requested.")

    # ------------------------------------------------- action dispatch
    def _dispatch(self, action: Action) -> str:
        at = action.action_type
        p = action.params

        if at == ActionType.execute_sql:
            return self._exec_sql(p.get("sql", ""))

        if at == ActionType.get_schema:
            return self._get_schema_text()

        if at == ActionType.get_table_info:
            return self._get_table_info(p.get("table", ""))

        if at == ActionType.submit:
            sql = p.get("sql")
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
                
                # FIX: Set the success flag if task-0 is solved
                if rows and self.current_task_id == "task-0":
                    sql_upper = sql.upper()
                    # Check if they fixed the ANDD typo
                    if "SELECT" in sql_upper and "USERS" in sql_upper and "AND" in sql_upper and "ANDD" not in sql_upper:
                        setattr(self.conn, "_easy_solved", True)
                
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
            return "Table name required."
        try:
            cur = self.conn.execute(f"PRAGMA table_info('{table}')")
            info = cur.fetchall()
            if not info:
                return f"Table '{table}' not found."
            
            summary = []
            for col in info:
                summary.append(f"{col[1]} ({col[2]})")
            
            cur = self.conn.execute(f"SELECT COUNT(*) FROM {table}")
            cnt = cur.fetchone()[0]
            
            return f"Table: {table}\nRows: {cnt}\nColumns: {', '.join(summary)}"
        except Exception as e:
            return f"Error getting table info: {e}"

    def _build_obs(self, last_result: str) -> Observation:
        task = TASKS[self.current_task_id]
        
        # Get schema metadata
        schema_meta = []
        try:
            cur = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            for t in tables:
                col_cur = self.conn.execute(f"PRAGMA table_info('{t}')")
                cols = [c[1] for c in col_cur.fetchall()]
                cnt_cur = self.conn.execute(f"SELECT COUNT(*) FROM {t}")
                cnt = cnt_cur.fetchone()[0]
                schema_meta.append(TableSummary(table_name=t, columns=cols, row_count=cnt))
        except:
            pass

        return Observation(
            result_set=None,
            error_message=None,
            schema_metadata=schema_meta,
            last_action_result=last_result,
            task_description=task.description,
            broken_query=task.get_broken_query()
        )

    def _build_step_response(self, score: float, reason: str, msg: str) -> StepResponse:
        reward = Reward(value=score, reason=reason)
        return StepResponse(
            observation=self._build_obs(msg),
            reward=reward,
            done=self.done,
            info={"step": self.step_count}
        )
