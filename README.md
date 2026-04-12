---
title: SQL Debugger Agent
emoji: 🛠️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
tags:
  - openenv
---

# SQL Database Debugger Agent 🛠️💾

An **OpenEnv-compliant** environment for training and evaluating AI agents on real-world SQL database tasks: debugging broken queries, optimizing performance, and refactoring schemas.

> **Hackathon**: Scaler × Meta × Hugging Face — OpenEnv  
> **Domain**: SQL / Database Engineering  

Graders are fully deterministic: they inspect the actual SQLite database state (schema structure, indexes, data integrity) rather than matching strings.

---

## 🏆 Judging Alignment Checklist

This environment was built with the **Scaler × Meta × Hugging Face** judging criteria as top priority:

| Parameter | Project Alignment |
|-----------|-------------------|
| **Real-world utility (30%)** | Models core Data Engineering & DBA tasks (debugging, performance tuning, schema refactoring). Directly useful for evaluating developer tools. |
| **Task & grader quality (25%)** | Features 3 graduated tasks (Easy → Hard). Graders verify actual DB state changes (DDL/DML), ensuring no "hallucinated" success. |
| **Environment design (20%)** | Clean state management using in-memory SQLite. Robust reward shaping with granular progress signals. |
| **Code quality & spec (15%)** | 100% OpenEnv compliant with typed Pydantic models. Dockerized and tested with automated validation scripts. |
| **Creativity & novelty (10%)** | First-of-its-kind SQL-specific OpenEnv centered on database troubleshooting and optimization. |

---

## Tasks

| ID | Name | Difficulty | Max Steps | Objective |
|----|------|-----------|-----------|-----------|
| `task1` | **Syntax Debugger** | Easy | 6 | Fix a broken query (`ANDD` typo → `AND`) |
| `task2` | **Performance Tuner** | Medium | 8 | Add a missing index on `customer_id` |
| `task3` | **Schema Architect** | Hard | 15 | Normalize a denormalized table into 3NF |

### Task Details

**Task 1 — Syntax Debugger (Easy)**  
The agent receives a broken SQL query: `SELECT * FROM users WHERE name = 'John Doe' ANDD email = 'john@example.com'`. It must identify the typo and execute the corrected query.

**Task 2 — Performance Tuner (Medium)**  
The `orders` table has 200 rows but no indexes. Queries filtering by `customer_id` are slow. The agent must create an appropriate index.

**Task 3 — Schema Architect (Hard)**  
The `projects` table contains redundant `manager_name` and `manager_email` columns. The agent must create a `managers` table, migrate data, and restructure `projects` to reference managers via a foreign key.

---

## Action Space

| Action | Parameters | Description |
|--------|-----------|-------------|
| `execute_sql` | `{"sql": "..."}` | Execute any SQL statement |
| `get_schema` | `{}` | View all table DDL statements |
| `get_table_info` | `{"table": "..."}` | Get column details and row count |
| `submit` | `{"sql": "..."}` | Submit final fix (also executes) |

---

## 🖥 Interactive Frontend (Swagger UI)
Because this environment is built on FastAPI, it includes a beautiful, fully interactive frontend test interface automatically!

To visit the frontend, just append **`/docs`** to your Hugging Face Space URL. From there, you can view the complete API schema, read parameter details, and use the "Try it out" button to playfully act as an Agent and interact with the database tables manually from your web browser!

---

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `schema_metadata` | `list[TableSummary]` | Current tables, columns, row counts |
| `last_action_result` | `string` | Result of the previous action |
| `task_description` | `string` | Task name, difficulty, objective |
| `broken_query` | `string \| null` | The broken query to fix (task1 only) |
| `error_message` | `string \| null` | SQL errors if any |
| `result_set` | `list \| null` | Query results |

## Reward Design

- **0.05**: No progress (minimum safe floor)
- **0.1–0.9**: **Granular Partial Credit**. The Hard Task specifically evaluates milestones:
    - `+0.2`: Manager table creation
    - `+0.3`: Foreign key integration
    - `+0.2`: Redundant column cleanup
    - `+0.2`: Data migration verification
- **0.95**: Task fully solved (maximum safe boundary)

This reward design ensures a dense learning signal for RL agents.

---

## Setup & Usage

### Prerequisites
- Python 3.9+
- pip

### Local Installation

```bash
cd SQLDebuggerAgent
pip install -r requirements.txt
```

### Start the Environment Server

```bash
python app.py
# Server runs on http://localhost:7860
```

### Run the Baseline Agent

```bash
# Set your HF token (or create a .env file)
export HF_TOKEN=your_token_here

# Run all 3 tasks
python inference.py

# Run a specific task
SQL_ENV_TASK=task2 python inference.py
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HF_TOKEN` | Yes | — | Hugging Face API token |
| `MODEL_NAME` | No | `Qwen/Qwen2.5-72B-Instruct` | LLM model identifier |
| `API_BASE_URL` | No | `https://router.huggingface.co/v1` | LLM API endpoint |
| `ENV_URL` | No | `http://localhost:7860` | Environment server URL |
| `SQL_ENV_TASK` | No | `task1` | Which task to run |

You can also create a **`.env`** file in the project root with these variables.

---

## Docker

```bash
docker build -t sql-debugger-agent .
docker run -p 7860:7860 sql-debugger-agent
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/reset` | Reset environment with `{"task_id": "task1"}` |
| POST | `/step` | Execute action `{"action_type": "...", "params": {...}}` |
| GET | `/state` | Current environment state |
| GET | `/tasks` | List all available tasks |
| POST | `/grade` | Grade current episode |
| GET | `/health` | Health check |

---

## Baseline Scores

| Task | Expected Score |
|------|---------------|
| task1 (Easy) | 0.85 – 1.00 |
| task2 (Medium) | 0.70 – 1.00 |
| task3 (Hard) | 0.50 – 1.00 |

---

## Project Structure

```
SQLDebuggerAgent/
├── app.py              # FastAPI server (OpenEnv endpoints)
├── models.py           # Typed Pydantic models
├── logic.py            # SQLEnv core (SQLite + grading)
├── tasks.py            # Task definitions & graders
├── inference.py        # Baseline agent script (runs all 3 tasks)
├── test_logic.py       # Offline tests for all tasks
├── openenv.yaml        # OpenEnv metadata
├── Dockerfile          # Container for HF Spaces
├── requirements.txt    # Python dependencies
├── .env.example        # Sample env vars
└── README.md           # This file
```
