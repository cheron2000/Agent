"""Durable SQLite Checkpoint and Journaling Store for Autonomous Goal Execution.

Operates with SQLite Write-Ahead Logging (WAL) and strict transactional commits:
- Guarantees crash resilience: States are committed to disk before and after physical inputs.
- Tracks append-only action execution journal.
- Reconciles steps left in DISPATCHING after sudden process termination or power loss.
"""

from dataclasses import asdict
from enum import Enum
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set

try:
    from .goal_schema import ExecutionPlan, PlanStep, StepExecutionState, GoalStatus
except (ImportError, ValueError):
    from Planner.goal_schema import ExecutionPlan, PlanStep, StepExecutionState, GoalStatus

logger = logging.getLogger("planner.checkpoint_store")


class SQLiteCheckpointStore:
    """Thread-safe SQLite persistent store with WAL mode for execution journals and checkpoints."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to persistent workspace memory directory
            base_dir = Path(__file__).resolve().parent.parent / "memory"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "agent_state.db")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enforce WAL mode and fast synchronous writes
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. Goals table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    instruction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 2. Plan Steps table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_steps (
                    goal_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target_query TEXT,
                    status TEXT NOT NULL,
                    retry_count INT DEFAULT 0,
                    error_message TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (goal_id, step_id)
                );
            """)

            # 3. Append-only Action Journal table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS action_journal (
                    journal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    intent_json TEXT,
                    dispatch_json TEXT,
                    evidence_json TEXT,
                    recovery_json TEXT,
                    timestamp REAL NOT NULL
                );
            """)

            # 4. Checkpoints table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    active_window TEXT,
                    observation_id TEXT,
                    completed_steps TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp REAL NOT NULL
                );
            """)

            # 5. Compensations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compensations (
                    goal_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    timestamp REAL NOT NULL,
                    PRIMARY KEY (goal_id, step_id)
                );
            """)
            conn.commit()

    def has_goal(self, goal_id: str) -> bool:
        """Check whether a goal already exists in the store."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM goals WHERE goal_id = ? LIMIT 1;", (goal_id,)).fetchone()
            return row is not None

    def get_plan_steps(self, goal_id: str) -> Dict[str, Dict[str, Any]]:
        """Fetch all recorded steps for a goal as a mapping from step_id to record dict."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT step_id, action_type, target_query, status, retry_count, error_message, updated_at
                FROM plan_steps
                WHERE goal_id = ?;
                """,
                (goal_id,),
            )
            return {row["step_id"]: dict(row) for row in cursor.fetchall()}

    def get_completed_step_ids(self, goal_id: str) -> Set[str]:
        """Fetch the set of step IDs that have been successfully verified and completed."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT step_id FROM plan_steps WHERE goal_id = ? AND status = 'completed';",
                (goal_id,),
            )
            return {row["step_id"] for row in cursor.fetchall()}

    def load_plan(self, goal_id: str) -> Optional[ExecutionPlan]:
        """Load an execution plan from persistent storage with up-to-date step execution states."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT plan_json, status FROM goals WHERE goal_id = ?;",
                (goal_id,),
            ).fetchone()
            if not row:
                return None
            plan_data = json.loads(row["plan_json"])
            plan = ExecutionPlan.from_dict(plan_data)
            plan.status = GoalStatus(row["status"])

            # Overlay true persistent step states
            step_rows = conn.execute(
                "SELECT step_id, status, retry_count, error_message FROM plan_steps WHERE goal_id = ?;",
                (goal_id,),
            ).fetchall()
            for sr in step_rows:
                s = plan.get_step(sr["step_id"])
                if s:
                    s.status = StepExecutionState(sr["status"])
                    s.retry_count = sr["retry_count"]
                    s.error_message = sr["error_message"]
            return plan

    def save_plan(self, plan: ExecutionPlan, preserve_existing_states: bool = True):
        """Save execution plan and all its steps transactionally.
        
        If preserve_existing_states=True, already recorded states (completed, dispatching, failed, compensated)
        in SQLite are NEVER overwritten with default pending states on resume or restart.
        """
        with self._get_connection() as conn:
            now = time.time()
            conn.execute(
                """
                INSERT OR REPLACE INTO goals (goal_id, instruction, status, plan_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    plan.goal_id,
                    plan.instruction,
                    plan.status.value if isinstance(plan.status, Enum) else str(plan.status),
                    json.dumps(plan.to_dict()),
                    plan.created_at,
                    now,
                ),
            )

            existing_steps = {}
            if preserve_existing_states:
                rows = conn.execute("SELECT step_id, status FROM plan_steps WHERE goal_id = ?;", (plan.goal_id,)).fetchall()
                existing_steps = {r["step_id"]: r["status"] for r in rows}

            for step in plan.steps:
                effective_status = step.status.value if isinstance(step.status, Enum) else str(step.status)
                if preserve_existing_states and step.step_id in existing_steps:
                    db_status = existing_steps[step.step_id]
                    if db_status in ("completed", "dispatching", "failed", "compensated") and effective_status == "pending":
                        effective_status = db_status
                        step.status = StepExecutionState(db_status)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO plan_steps (goal_id, step_id, action_type, target_query, status, retry_count, error_message, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        plan.goal_id,
                        step.step_id,
                        step.action_type,
                        step.target_query,
                        effective_status,
                        step.retry_count,
                        step.error_message,
                        now,
                    ),
                )
            conn.commit()

    def record_pre_dispatch(self, goal_id: str, step_id: str, intent_dict: Optional[Dict[str, Any]] = None):
        """
        CRITICAL CHECKPOINT PROTOCOL STEP:
        Record and commit DISPATCHING state BEFORE issuing real OS mouse/keyboard actions.
        """
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE plan_steps
                SET status = 'dispatching', updated_at = ?
                WHERE goal_id = ? AND step_id = ?;
                """,
                (now, goal_id, step_id),
            )
            conn.execute(
                """
                INSERT INTO action_journal (goal_id, step_id, state, intent_json, timestamp)
                VALUES (?, ?, 'dispatching', ?, ?);
                """,
                (goal_id, step_id, json.dumps(intent_dict or {}), now),
            )
            conn.commit()

    def record_dispatch_result(self, goal_id: str, step_id: str, dispatch_result: Dict[str, Any]):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO action_journal (goal_id, step_id, state, dispatch_json, timestamp)
                VALUES (?, ?, 'dispatched', ?, ?);
                """,
                (goal_id, step_id, json.dumps(dispatch_result), now),
            )
            conn.commit()

    def record_verification(
        self,
        goal_id: str,
        step_id: str,
        status: str,
        evidence_dict: Dict[str, Any],
        recovery_dict: Optional[Dict[str, Any]] = None,
    ):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE plan_steps
                SET status = ?, updated_at = ?
                WHERE goal_id = ? AND step_id = ?;
                """,
                (status, now, goal_id, step_id),
            )
            conn.execute(
                """
                INSERT INTO action_journal (goal_id, step_id, state, evidence_json, recovery_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    goal_id,
                    step_id,
                    status,
                    json.dumps(evidence_dict),
                    json.dumps(recovery_dict or {}),
                    now,
                ),
            )
            conn.commit()

    def save_checkpoint(
        self,
        goal_id: str,
        step_id: str,
        active_window: str,
        observation_id: str,
        completed_steps: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        checkpoint_id = f"chk_{goal_id}_{step_id}_{int(time.time()*1000)}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (checkpoint_id, goal_id, step_id, active_window, observation_id, completed_steps, metadata_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    checkpoint_id,
                    goal_id,
                    step_id,
                    active_window,
                    observation_id,
                    json.dumps(completed_steps),
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            conn.commit()
        return checkpoint_id

    def get_crashed_steps(self, goal_id: str) -> List[Dict[str, Any]]:
        """Identify any step stranded in DISPATCHING from an unexpected process kill."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT step_id, action_type, target_query, status, retry_count, updated_at
                FROM plan_steps
                WHERE goal_id = ? AND status = 'dispatching';
                """,
                (goal_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def record_compensation(
        self,
        goal_id: str,
        step_id: str,
        action_type: str,
        action_dict: Dict[str, Any],
        status: str,
        result_dict: Optional[Dict[str, Any]] = None,
    ):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compensations (goal_id, step_id, action_type, action_json, status, result_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    goal_id,
                    step_id,
                    action_type,
                    json.dumps(action_dict),
                    status,
                    json.dumps(result_dict or {}),
                    now,
                ),
            )
            conn.commit()

    def update_goal_status(self, goal_id: str, status: GoalStatus):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE goals
                SET status = ?, updated_at = ?
                WHERE goal_id = ?;
                """,
                (status.value if isinstance(status, Enum) else str(status), now, goal_id),
            )
            conn.commit()

    def get_latest_checkpoint(self, goal_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT checkpoint_id, goal_id, step_id, active_window, observation_id, completed_steps, metadata_json, timestamp
                FROM checkpoints
                WHERE goal_id = ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT 1;
                """,
                (goal_id,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["completed_steps"] = json.loads(d["completed_steps"])
                d["metadata"] = json.loads(d.pop("metadata_json", "{}"))
                return d
            return None
