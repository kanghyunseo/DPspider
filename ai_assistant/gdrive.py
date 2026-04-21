"""Google Drive wrapper — upload Markdown as Google Docs."""
import io

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .google_auth import load_credentials


def get_service(credentials_path: str, token_path: str):
    creds = load_credentials(credentials_path, token_path)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class Drive:
    def __init__(self, service, folder_id: str | None = None):
        self.service = service
        self.folder_id = folder_id

    def upload_markdown_as_doc(self, filename: str, markdown: str) -> dict:
        """Upload Markdown content as a Google Doc (auto-converted).

        Returns dict with id, name, webViewLink.
        """
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
