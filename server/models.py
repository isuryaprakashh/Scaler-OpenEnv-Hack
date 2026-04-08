from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    execute_sql = "execute_sql"
    get_schema = "get_schema"
    get_table_info = "get_table_info"
    submit = "submit"


class Action(BaseModel):
    action_type: ActionType
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the action. e.g., {'sql': 'SELECT * FROM users'}",
    )


class TableSummary(BaseModel):
    table_name: str
    columns: List[str]
    row_count: int


class Observation(BaseModel):
    result_set: Optional[List[Dict[str, Any]]] = None
    error_message: Optional[str] = None
    schema_metadata: Optional[List[TableSummary]] = None
    last_action_result: Optional[str] = None
    task_description: str
    broken_query: Optional[str] = None


class Reward(BaseModel):
    value: float = Field(ge=0.0, le=1.0)
    reason: str
    partial_credits: Dict[str, float] = Field(default_factory=dict)


class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: Dict[str, Any]
