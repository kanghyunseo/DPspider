"""Shared Google OAuth credentials.

Holds the scope list and the credential-loading logic used by both
Calendar and Drive clients. When scopes change, users must re-run
authenticate_gcal.py to regenerate token.json.
"""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/tasks",
]


def load_credentials(credentials_path: str, token_path: str) -> Credentials:
    """Load authorized user credentials, refreshing if needed.

    Raises RuntimeError with a clear message when the token file is
    missing or scopes don't match (user needs to re-authenticate).
    """
    if not os.path.exists(token_path):
        raise RuntimeError(
            f"Token not found at {token_path}. "
            f"Run `python authenticate_gcal.py` first "
            f"(locally) or set GOOGLE_TOKEN_JSON (cloud)."
        )

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        try:
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        except OSError:
            pass  # read-only filesystem; refresh works in memory
        return creds

    raise RuntimeError(
        "Google credentials invalid and cannot be refreshed. "
        "Re-run `python authenticate_gcal.py` to re-authorize."
    )
