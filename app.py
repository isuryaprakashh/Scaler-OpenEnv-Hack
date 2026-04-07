from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from models import Action, StepResponse, Observation
from logic import SQLEnv
from tasks import TASKS

app = FastAPI(title="SQL Database Debugger Agent", version="1.0.0")
env = SQLEnv()


class ResetRequest(BaseModel):
    task_id: str = "task1"


@app.post("/reset")
async def reset(request: Optional[ResetRequest] = None):
    task_id = request.task_id if request else "task1"
    if task_id not in TASKS:
        raise HTTPException(status_code=400, detail=f"Unknown task: {task_id}")
    obs = env.reset(task_id)
    return obs.model_dump()


@app.post("/step")
async def step(action: Action):
    if not env.current_task_id:
        raise HTTPException(status_code=400, detail="Call /reset first.")
    resp = env.step(action)
    return resp.model_dump()


@app.get("/state")
async def state():
    if not env.current_task_id:
        raise HTTPException(status_code=400, detail="Call /reset first.")
    return env.state()


@app.get("/tasks")
async def list_tasks():
    return [
        {
            "id": t.id,
            "name": t.name,
            "difficulty": t.difficulty,
            "description": t.description,
            "objective": t.objective,
            "max_steps": t.max_steps,
        }
        for t in TASKS.values()
    ]


@app.post("/grade")
async def grade():
    if not env.current_task_id:
        raise HTTPException(status_code=400, detail="Call /reset first.")
    task = TASKS[env.current_task_id]
    score, reason = task.grade(env.conn)
    return {
        "task_id": env.current_task_id,
        "score": score,
        "reason": reason,
        "resolved": score >= 1.0,
        "steps_used": env.step_count,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
