"""Google Tasks wrapper — task creation, status updates, listing."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from googleapiclient.discovery import build

from .google_auth import load_credentials


def get_service(credentials_path: str, token_path: str):
    creds = load_credentials(credentials_path, token_path)
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


class Tasks:
    """Operations on a single Google Tasks list (default: '@default')."""

    def __init__(self, service, tasklist_id: str = "@default"):
        self.service = service
        self.tasklist_id = tasklist_id

    # ---------- read ----------

    def list_tasks(
        self,
        show_completed: bool = False,
        completed_min: str | None = None,
        completed_max: str | None = None,
        due_min: str | None = None,
        due_max: str | None = None,
        max_results: int = 100,
    ) -> list[dict]:
        """List tasks. All datetime params are RFC 3339 (e.g. 2026-04-22T00:00:00Z).

        - show_completed=False (default) returns only open tasks.
        - completed_min/max filter on completion timestamp; setting them
          implies show_completed=True and showHidden=True.
        """
        params: dict = {
            "tasklist": self.tasklist_id,
            "showCompleted": show_completed,
            "showHidden": False,
            "maxResults": max_results,
        }
        if completed_min or completed_max:
            params["showCompleted"] = True
            params["showHidden"] = True
            if completed_min:
                params["completedMin"] = completed_min
            if completed_max:
                params["completedMax"] = completed_max
        if due_min:
            params["dueMin"] = due_min
        if due_max:
            params["dueMax"] = due_max

        items = self.service.tasks().list(**params).execute().get("items", [])
        return [_summarize(t) for t in items]

    # ---------- write ----------

    def create_task(
        self,
        title: str,
        notes: str | None = None,
        due: str | None = None,
    ) -> dict:
        """Create a task. due is RFC 3339; Google Tasks ignores time-of-day."""
        body: dict = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due
        created = (
            self.service.tasks()
            .insert(tasklist=self.tasklist_id, body=body)
            .execute()
        )
        return _summarize(created)

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        due: Optional[str] = None,
        status: Optional[str] = None,  # "needsAction" or "completed"
    ) -> dict:
        body: dict = {"id": task_id}
        if title is not None:
            body["title"] = title
        if notes is not None:
            body["notes"] = notes
        if due is not None:
            body["due"] = due
        if status is not None:
            body["status"] = status
        updated = (
            self.service.tasks()
            .patch(tasklist=self.tasklist_id, task=task_id, body=body)
            .execute()
        )
        return _summarize(updated)

    def complete_task(self, task_id: str) -> dict:
        return self.update_task(task_id, status="completed")

    def reopen_task(self, task_id: str) -> dict:
        # Google requires clearing the `completed` field when reopening
        body = {"id": task_id, "status": "needsAction", "completed": None}
        updated = (
            self.service.tasks()
            .patch(tasklist=self.tasklist_id, task=task_id, body=body)
            .execute()
        )
        return _summarize(updated)

    def delete_task(self, task_id: str) -> dict:
        self.service.tasks().delete(
            tasklist=self.tasklist_id, task=task_id
        ).execute()
        return {"deleted": task_id}


def _summarize(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "title": t.get("title"),
        "notes": t.get("notes"),
        "due": t.get("due"),
        "status": t.get("status"),
        "completed": t.get("completed"),
        "updated": t.get("updated"),
    }


def is_overdue(task: dict, now: datetime) -> bool:
    """True if task is open and its due date is before `now`."""
    if task.get("status") == "completed":
        return False
    due = task.get("due")
    if not due:
        return False
    try:
        dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt < now
