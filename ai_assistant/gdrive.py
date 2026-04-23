"""Google Drive wrapper — upload Markdown as Google Docs and arbitrary files."""
from __future__ import annotations

import io
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

from .google_auth import load_credentials


def get_service(credentials_path: str, token_path: str):
    creds = load_credentials(credentials_path, token_path)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class Drive:
    def __init__(self, service, folder_id: str | None = None):
        self.service = service
        self.folder_id = folder_id

    def upload_markdown_as_doc(self, filename: str, markdown: str) -> dict:
        """Upload Markdown content as a Google Doc (auto-converted)."""
        media = MediaIoBaseUpload(
            io.BytesIO(markdown.encode("utf-8")),
            mimetype="text/markdown",
            resumable=False,
        )
        body = {
            "name": filename,
            "mimeType": "application/vnd.google-apps.document",
        }
        if self.folder_id:
            body["parents"] = [self.folder_id]

        created = (
            self.service.files()
            .create(body=body, media_body=media, fields="id,name,webViewLink")
            .execute()
        )
        return {
            "id": created["id"],
            "name": created["name"],
            "link": created["webViewLink"],
        }

    def upload_file(
        self,
        local_path: str | Path,
        drive_filename: str | None = None,
        mime_type: str = "application/octet-stream",
        folder_id: str | None = None,
    ) -> dict:
        """Upload a local file as-is (no conversion). Returns id/name/link."""
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(local_path)
        target_folder = folder_id or self.folder_id
        body = {"name": drive_filename or local_path.name}
        if target_folder:
            body["parents"] = [target_folder]
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)
        created = (
            self.service.files()
            .create(body=body, media_body=media, fields="id,name,webViewLink")
            .execute()
        )
        return {
            "id": created["id"],
            "name": created["name"],
            "link": created["webViewLink"],
        }

    def find_or_create_folder(self, name: str, parent_id: str | None = None) -> str:
        """Return folder id. Look up by name within parent (or root); create if missing."""
        query_parts = [
            f"name = '{name}'",
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false",
        ]
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        results = (
            self.service.files()
            .list(q=" and ".join(query_parts), fields="files(id,name)", pageSize=10)
            .execute()
            .get("files", [])
        )
        if results:
            return results[0]["id"]
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        created = self.service.files().create(body=body, fields="id").execute()
        return created["id"]

    def list_files_in_folder(
        self, folder_id: str, name_prefix: str | None = None
    ) -> list[dict]:
        """List files in a folder. Returns id/name/createdTime."""
        query_parts = [f"'{folder_id}' in parents", "trashed = false"]
        if name_prefix:
            query_parts.append(f"name contains '{name_prefix}'")
        return (
            self.service.files()
            .list(
                q=" and ".join(query_parts),
                fields="files(id,name,createdTime)",
                pageSize=200,
                orderBy="createdTime desc",
            )
            .execute()
            .get("files", [])
        )

    def delete_file(self, file_id: str) -> None:
        self.service.files().delete(fileId=file_id).execute()
