"""One-time Google Calendar OAuth setup.

Run once:
    python -m ai_assistant.authenticate_gcal

Prerequisites:
    1. Go to https://console.cloud.google.com/apis/credentials
    2. Create a project → Enable Google Calendar API
    3. Create OAuth 2.0 Client ID (application type: Desktop app)
    4. Download the JSON and save it as `credentials.json`
"""
if __name__ == "__main__" and __package__ in (None, ""):
    import pathlib
    import sys

    _pkg_dir = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(_pkg_dir.parent))
    __package__ = _pkg_dir.name

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
    token_content = creds.to_json()
    with open(token_path, "w") as f:
        f.write(token_content)

    print()
    print("=" * 72)
    print(f"✅ Token saved to {token_path}")
    print("=" * 72)
    print()
    print("☁️  Railway 등 클라우드 배포용 — 아래 JSON 전체(한 줄)를 복사해서")
    print("    GOOGLE_TOKEN_JSON 환경변수에 붙여넣으세요:")
    print()
    print("-" * 72)
    print(token_content)
    print("-" * 72)


if __name__ == "__main__":
    main()
