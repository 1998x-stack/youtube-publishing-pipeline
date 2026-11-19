"""Single user OAuth credential for Drive-readonly and the approved YouTube channel.

OAuth is interactive only for 'ytp auth'; Cloud Run uses pre-provisioned refresh
tokens from Secret Manager (not included in this local reference adapter).
"""
from __future__ import annotations

import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def credentials(*, interactive: bool = False) -> Credentials:
    path = Path(os.getenv("YTP_TOKEN_FILE", "./secrets/token.json"))
    client = Path(os.getenv("YTP_OAUTH_CLIENT_FILE", "./secrets/client_secret.json"))
    creds = Credentials.from_authorized_user_file(str(path), SCOPES) if path.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interactive:
        if not client.exists():
            raise FileNotFoundError(f"OAuth client file not found: {client}")
        creds = InstalledAppFlow.from_client_secrets_file(
            str(client), SCOPES
        ).run_local_server(port=0, access_type="offline", prompt="consent")
    else:
        raise RuntimeError("OAuth missing or invalid. Run 'ytp auth' locally first.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return creds
