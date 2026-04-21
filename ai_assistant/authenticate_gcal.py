"""One-time Google Calendar OAuth setup.

Run once:
    python -m ai_assistant.authenticate_gcal

Prerequisites:
    1. Go to https://console.cloud.google.com/apis/credentials
    2. Create a project → Enable Google Calendar API
    3. Create OAuth 2.0 Client ID (application type: Desktop app)
    4. Download the JSON and save it as `credentials.json`
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from . import config
from .gcal import SCOPES


def main() -> None:
    creds_path = config.GOOGLE_CREDENTIALS_PATH
    token_path = config.GOOGLE_TOKEN_PATH

    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"{creds_path} not found. "
            "Download OAuth client credentials from Google Cloud Console "
            "(Desktop app type) and save as credentials.json."
        )

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    print(f"✅ Token saved to {token_path}")


if __name__ == "__main__":
    main()
