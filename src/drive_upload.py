import io
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service_oauth():
    """
    Builds a Drive service using OAuth refresh token (works with personal Gmail Drive).
    Requires env vars:
      GOOGLE_OAUTH_CLIENT_ID
      GOOGLE_OAUTH_CLIENT_SECRET
      GOOGLE_OAUTH_REFRESH_TOKEN
    """
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")

    missing = [k for k, v in [
        ("GOOGLE_OAUTH_CLIENT_ID", client_id),
        ("GOOGLE_OAUTH_CLIENT_SECRET", client_secret),
        ("GOOGLE_OAUTH_REFRESH_TOKEN", refresh_token),
    ] if not v]
    if missing:
        raise SystemExit(f"Missing OAuth env vars: {', '.join(missing)}")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    # Ensure we have a valid access token
    creds.refresh(Request())

    return build("drive", "v3", credentials=creds, cache_discovery=False)

def find_or_create_folder(service, name: str, parent_id: str) -> str:
    safe_name = name.replace("'", "")
    q = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{safe_name}' "
        f"and '{parent_id}' in parents "
        "and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id,name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=meta, fields="id").execute()
    return created["id"]

def upload_bytes(service, parent_id: str, filename: str, content: bytes, mime_type: str) -> str:
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=True)
    meta = {"name": filename, "parents": [parent_id]}
    created = service.files().create(body=meta, media_body=media, fields="id").execute()
    return created["id"]

def upload_text(service, parent_id: str, filename: str, text: str) -> str:
    return upload_bytes(
        service,
        parent_id=parent_id,
        filename=filename,
        content=text.encode("utf-8"),
        mime_type="text/plain",
    )
