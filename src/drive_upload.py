import io
from typing import Optional, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

def _drive_service(service_account_json: str):
    creds = service_account.Credentials.from_service_account_info(
        eval(service_account_json) if service_account_json.strip().startswith("{") else None
    )

def get_drive_service(service_account_json_text: str):
    # service_account_info expects a dict, not a string
    import json
    info = json.loads(service_account_json_text)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def find_or_create_folder(service, name: str, parent_id: str) -> str:
    # Clean name to avoid quote issues in Drive query
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
