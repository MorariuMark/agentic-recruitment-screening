"""
backend/services/progress_tracker.py
Thread-safe live progress tracker for long-running AI agent operations.
Tracks real execution steps, requirement completion counts, and phase descriptions
so the frontend progress bar reflects true backend state instead of a static timer.
"""

import threading
import time
from typing import Any, Dict, List, Optional


class ProgressTracker:
    """Thread-safe registry of active AI processing tasks and their step-by-step progress."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._latest_key: Optional[str] = None

    def start_task(
        self,
        task_key: str,
        label: str,
        phase: str,
        total_steps: int = 4,
    ) -> None:
        now = time.time()
        with self._lock:
            self._tasks[task_key] = {
                "task_key": task_key,
                "active": True,
                "label": label,
                "phase": phase,
                "completed_steps": 0,
                "total_steps": max(1, total_steps),
                "percentage": 5.0,
                "completed_items": [],
                "started_at": now,
                "updated_at": now,
            }
            self._latest_key = task_key

    def update_task(
        self,
        task_key: str,
        completed_steps: Optional[int] = None,
        total_steps: Optional[int] = None,
        phase: Optional[str] = None,
        percentage: Optional[float] = None,
        item_completed: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._lock:
            task = self._tasks.get(task_key)
            if not task:
                return
            if total_steps is not None and total_steps > 0:
                task["total_steps"] = total_steps
            if completed_steps is not None:
                task["completed_steps"] = min(completed_steps, task["total_steps"])
            if phase is not None:
                task["phase"] = phase
            if item_completed:
                task["completed_items"].append(item_completed)

            if percentage is not None:
                task["percentage"] = max(0.0, min(100.0, round(percentage, 1)))
            else:
                tot = max(1, task["total_steps"])
                comp = task["completed_steps"]
                task["percentage"] = round(min(98.0, max(5.0, (comp / tot) * 100.0)), 1)

            task["updated_at"] = now
            self._latest_key = task_key

    def increment_step(
        self,
        task_key: str,
        phase: Optional[str] = None,
        item_completed: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._lock:
            task = self._tasks.get(task_key)
            if not task:
                return
            task["completed_steps"] = min(task["completed_steps"] + 1, task["total_steps"])
            if phase is not None:
                task["phase"] = phase
            if item_completed:
                task["completed_items"].append(item_completed)

            tot = max(1, task["total_steps"])
            comp = task["completed_steps"]
            task["percentage"] = round(min(98.0, max(5.0, (comp / tot) * 100.0)), 1)
            task["updated_at"] = now
            self._latest_key = task_key

    def finish_task(self, task_key: str, phase: str = "Completed") -> None:
        now = time.time()
        with self._lock:
            task = self._tasks.get(task_key)
            if not task:
                return
            task["active"] = False
            task["completed_steps"] = task["total_steps"]
            task["percentage"] = 100.0
            task["phase"] = phase
            task["updated_at"] = now

    def get_active_progress(self, task_key: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if task_key:
                candidates_keys = [task_key]
                if task_key == "match_evaluation":
                    candidates_keys.append("candidate_evaluation")
                elif task_key == "candidate_evaluation":
                    candidates_keys.append("match_evaluation")
                for k in candidates_keys:
                    if k in self._tasks and self._tasks[k].get("active"):
                        return dict(self._tasks[k])
                for k in candidates_keys:
                    if k in self._tasks:
                        return dict(self._tasks[k])

            # Prefer any currently active task
            for k in reversed(list(self._tasks.keys())):
                t = self._tasks[k]
                if t.get("active"):
                    return dict(t)

            if self._latest_key and self._latest_key in self._tasks:
                return dict(self._tasks[self._latest_key])

            return {
                "task_key": "none",
                "active": False,
                "label": "Idle",
                "phase": "Ready",
                "completed_steps": 0,
                "total_steps": 1,
                "percentage": 0.0,
                "completed_items": [],
                "started_at": 0.0,
                "updated_at": 0.0,
            }


progress_tracker = ProgressTracker()
