"""YouTube Data API v3 upload — OPTIONAL. Never blocks production.

Setup: create OAuth client (Desktop) in Google Cloud Console, enable YouTube Data API v3,
download client_secrets.json, set YOUTUBE_CLIENT_SECRETS to its path. First run opens a
browser/URL for one-time consent; token cached at YOUTUBE_TOKEN_FILE.
Quota: uploads cost ~1600 units; default project quota 10,000 units/day (free).
"""
from __future__ import annotations
from pathlib import Path


def upload_status() -> dict:
    from ..config import get_settings
    cfg = get_settings()
    try:
        import googleapiclient  # noqa
        lib = True
    except Exception:
        lib = False
    return {
        "library_installed": lib,
        "client_secrets_set": bool(cfg.youtube_client_secrets and Path(cfg.youtube_client_secrets).exists()),
        "token_exists": Path(cfg.youtube_token_file).exists(),
        "note": "pip install google-api-python-client google-auth-oauthlib to enable",
    }


def upload_video(video_path: str, title: str, description: str, tags: list[str],
                 privacy: str = "private") -> dict:
    """Returns real API result. Raises with clear guidance if not configured."""
    st = upload_status()
    if not st["library_installed"]:
        raise RuntimeError("YouTube upload not installed: pip install google-api-python-client google-auth-oauthlib")
    from ..config import get_settings
    cfg = get_settings()
    if not st["client_secrets_set"]:
        raise RuntimeError("YOUTUBE_CLIENT_SECRETS not set — see docs/YOUTUBE_UPLOAD.md")
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import pickle
    token_p = Path(cfg.youtube_token_file)
    creds = None
    if token_p.exists():
        try:
            import json
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(token_p))
        except Exception:
            creds = None
    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(
            cfg.youtube_client_secrets,
            scopes=["https://www.googleapis.com/auth/youtube.upload"])
        creds = flow.run_console()
        token_p.write_text(creds.to_json(), encoding="utf-8")
    yt = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title[:100], "description": description[:5000],
                        "tags": tags[:30], "categoryId": "27"},
            "status": {"privacyStatus": privacy if privacy in ("private", "unlisted", "public") else "private"}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video_path, resumable=True))
    resp = req.execute()
    vid = resp.get("id", "")
    return {"video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}" if vid else "",
            "privacy": privacy, "raw_status": resp.get("status", {})}
