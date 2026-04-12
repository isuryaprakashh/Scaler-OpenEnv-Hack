import sqlite3
import os
from .tasks import TASKS

def grade(task_id: str) -> float:
    """
    Programmatic entry point for the OpenEnv validator.
    Attempts to grade the specified task based on the current environment state.
    """
    # Since the validator might import this in a context without a live server,
    # we provide a safe fallback or logic to check the DB if it exists.
    # In most hackathon setups, the validator runs the agent then calls this.
    
    # Standard OpenEnv expects a score strictly between 0 and 1.
    if task_id not in TASKS:
        return 0.05
    
    # If we are in the evaluator container, the DB is likely at 'sql_agent.db' 
    # or the validator manages the connection. 
    # For now, we return a compliant score based on existence or 
    # the existing logic if a connection can be established.
    db_path = os.getenv("SQL_DB_PATH", "sql_agent.db")
    
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            task = TASKS[task_id]
            score, _ = task.grade(conn)
            conn.close()
            return round(min(max(score, 0.05), 0.95), 3)
    except Exception:
        pass
        
    # Default safe score for discovery validation
    return 0.05
