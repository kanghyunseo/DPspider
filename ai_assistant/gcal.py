"""Google Calendar wrapper — thin helpers around the Calendar v3 API."""
from __future__ import annotations

from googleapiclient.discovery import build

from .google_auth import SCOPES, load_credentials  # noqa: F401  (re-export)


def get_service(credentials_path: str, token_path: str):
    creds = load_credentials(credentials_path, token_path)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


class Calendar:
    def __init__(self, service, calendar_id: str, timezone: str):
        self.service = service
        self.calendar_id = calendar_id
        self.timezone = timezone

    def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        recurrence: list[str] | None = None,
    ) -> dict:
        body = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": self.timezone},
            "end": {"dateTime": end_datetime, "timeZone": self.timezone},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]
        if recurrence:
            body["recurrence"] = recurrence

        created = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )
        return _summarize(created)

    def list_events(
        self,
        time_min: str,
        time_max: str,
        max_results: int = 20,
        query: str | None = None,
    ) -> list[dict]:
        params = {
            "calendarId": self.calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": self.timezone,
        }
        if query:
            params["q"] = query
        events = (
            self.service.events().list(**params).execute().get("items", [])
        )
        return [_summarize(ev) for ev in events]

    def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict:
        event = (
            self.service.events()
            .get(calendarId=self.calendar_id, eventId=event_id)
            .execute()
        )
        if summary is not None:
            event["summary"] = summary
        if start_datetime is not None:
            event["start"] = {"dateTime": start_datetime, "timeZone": self.timezone}
        if end_datetime is not None:
            event["end"] = {"dateTime": end_datetime, "timeZone": self.timezone}
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location

        updated = (
            self.service.events()
            .update(calendarId=self.calendar_id, eventId=event_id, body=event)
            .execute()
        )
        return _summarize(updated)

    def delete_event(self, event_id: str) -> dict:
        self.service.events().delete(
            calendarId=self.calendar_id, eventId=event_id
        ).execute()
        return {"deleted": event_id}


def _summarize(ev: dict) -> dict:
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary", "(제목 없음)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "htmlLink": ev.get("htmlLink"),
    }
