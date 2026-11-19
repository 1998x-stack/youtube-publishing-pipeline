from __future__ import annotations

import json

from youtube_pipeline.adapters import google_auth
from youtube_pipeline.cli import parser


def test_backend_selection_is_explicit(monkeypatch):
    monkeypatch.setenv("YTP_BACKEND", "firestore")
    args = parser().parse_args(["scan"])
    assert args.backend == "firestore"


def test_secret_manager_credentials_read_without_file_writes(monkeypatch, tmp_path):
    data = {
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "not-a-real-secret",
        "refresh_token": "fake-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": google_auth.SCOPES,
    }
    monkeypatch.setenv(
        "YTP_OAUTH_SECRET_RESOURCE",
        "projects/sample-project/secrets/ytp-youtube-oauth/versions/latest",
    )
    token = tmp_path / "must-not-write-token.json"
    monkeypatch.setenv("YTP_TOKEN_FILE", str(token))
    from google.cloud import secretmanager

    from types import SimpleNamespace
    response = SimpleNamespace(payload=SimpleNamespace(data=json.dumps(data).encode()))

    class FakeSecretClient:
        def access_secret_version(self, request):
            assert request["name"].endswith("/versions/latest")
            return response

    class FakeCredentials:
        valid = True
        refresh_token = "fake-refresh-token"

    monkeypatch.setattr(secretmanager, "SecretManagerServiceClient", FakeSecretClient)
    monkeypatch.setattr(
        google_auth.Credentials, "from_authorized_user_info",
        lambda *_: FakeCredentials(),
    )
    assert google_auth.credentials().valid
    assert not token.exists()
