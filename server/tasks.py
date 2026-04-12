import sqlite3
from typing import Any, Optional, Tuple


class Task:
    def __init__(self, id: str, name: str, difficulty: str, description: str,
                 objective: str, max_steps: int):
        self.id = id
        self.name = name
        self.difficulty = difficulty
        self.description = description
        self.objective = objective
        self.max_steps = max_steps

    def setup(self, conn: sqlite3.Connection):
        raise NotImplementedError

        return 0.05, "Not graded"

    def get_broken_query(self) -> Optional[str]:
        """Return the broken query the agent must fix (task1 only)."""
        return None


class EasyTask(Task):
    """Fix a broken SQL query that has a typo (ANDD instead of AND)."""

    BROKEN_QUERY = "SELECT * FROM users WHERE name = 'John Doe' ANDD email = 'john@example.com'"

    def setup(self, conn: sqlite3.Connection):
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        conn.execute("INSERT INTO users (name, email) VALUES ('John Doe', 'john@example.com')")
        conn.execute("INSERT INTO users (name, email) VALUES ('Jane Smith', 'jane@example.com')")
        conn.execute("INSERT INTO users (name, email) VALUES ('Bob Wilson', 'bob@example.com')")
        conn.commit()

    def get_broken_query(self) -> Optional[str]:
        return self.BROKEN_QUERY

    def grade(self, conn: sqlite3.Connection) -> Tuple[float, str]:
        # We check if the agent has successfully executed a corrected query.
        # The grade is called after every step, so we just check if a
        # "last_successful_select" flag was set on the connection.
        flag = getattr(conn, "_easy_solved", False)
        if flag:
            return 0.95, "Query fixed — correct results returned."
        return 0.05, "The broken query has not been fixed yet."


class MediumTask(Task):
    """Add a missing index on customer_id to optimize a slow query."""

    def setup(self, conn: sqlite3.Connection):
        conn.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, "
            "amount REAL, status TEXT, created_at TEXT)"
        )
        for i in range(200):
            conn.execute(
                "INSERT INTO orders (customer_id, amount, status, created_at) "
                f"VALUES ({i % 15}, {50 + (i * 1.5):.2f}, 'completed', '2024-01-{(i % 28)+1:02d}')"
            )
        conn.commit()

    def grade(self, conn: sqlite3.Connection) -> Tuple[float, str]:
        cursor = conn.execute("PRAGMA index_list('orders')")
        indexes = cursor.fetchall()
        for idx in indexes:
            idx_name = idx[1]
            info = conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
            cols = [c[2] for c in info]
            if "customer_id" in cols:
                return 0.95, "Index on customer_id created — query is now optimized."
        return 0.05, "No index on customer_id found yet."


class HardTask(Task):
    """Normalize a denormalized projects table into projects + managers."""

    def setup(self, conn: sqlite3.Connection):
        conn.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, project_name TEXT, "
            "manager_name TEXT, manager_email TEXT)"
        )
        rows = [
            ("Titan", "Alice", "alice@corp.com"),
            ("Aries", "Alice", "alice@corp.com"),
            ("Vega",  "Bob",   "bob@corp.com"),
            ("Nova",  "Carol", "carol@corp.com"),
            ("Orion", "Bob",   "bob@corp.com"),
        ]
        conn.executemany(
            "INSERT INTO projects (project_name, manager_name, manager_email) VALUES (?,?,?)",
            rows,
        )
        conn.commit()

    def grade(self, conn: sqlite3.Connection) -> Tuple[float, str]:
        # 1. Check managers table exists
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='managers'"
        )
        if not cur.fetchone():
            return 0.1, "No 'managers' table found. Create one first."

        # 2. Check projects table columns
        cur = conn.execute("PRAGMA table_info('projects')")
        proj_cols = [c[1] for c in cur.fetchall()]

        has_redundant = "manager_name" in proj_cols or "manager_email" in proj_cols
        has_fk = "manager_id" in proj_cols

        if has_redundant and not has_fk:
            return 0.4, "managers table exists but projects still has redundant columns."
        if has_redundant and has_fk:
            return 0.6, "manager_id added but redundant columns not removed."
        if not has_redundant and not has_fk:
            return 0.5, "Redundant columns removed but no manager_id foreign key."
        # has_fk and not has_redundant
        # 3. Verify data integrity
        cur = conn.execute("SELECT COUNT(*) FROM managers")
        mgr_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM projects")
        proj_count = cur.fetchone()[0]

        if mgr_count >= 2 and proj_count >= 4:
            return 0.95, "Schema fully normalized with correct data migration."
        return 0.8, "Schema normalized but data migration appears incomplete."


TASKS = {
    "task1": EasyTask(
        "task1", "Syntax Debugger", "easy",
        "A SQL query has a typo (ANDD instead of AND). Fix it so it returns correct results.",
        "Fix the broken SQL query to retrieve user data correctly.", 6
    ),
    "task2": MediumTask(
        "task2", "Performance Tuner", "medium",
        "The orders table has 200 rows but no indexes. Queries filtering by customer_id are slow.",
        "Add necessary indexes to optimize data retrieval on orders.", 8
    ),
    "task3": HardTask(
        "task3", "Schema Architect", "hard",
        "The projects table stores redundant manager info. Normalize it into separate tables.",
        "Split into projects and managers tables with a foreign key relationship.", 15
    ),
}
