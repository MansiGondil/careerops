"""
Gmail access, read-only.

Scope is gmail.readonly: the app cannot send, delete or modify anything.
Access is revocable at myaccount.google.com/permissions.

First run opens a browser for consent and writes token.json. After that
it refreshes silently, so the scheduled pipeline needs no interaction.
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_service():
    creds = None

    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS.exists():
                raise FileNotFoundError(
                    f"{CREDENTIALS} not found — download the OAuth client "
                    "JSON from Google Cloud Console"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)