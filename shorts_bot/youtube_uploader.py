"""
Uploads a video to YouTube via the official YouTube Data API v3.

One-time setup (see README): create an OAuth "Desktop app" client in Google Cloud,
save it as client_secret.json next to this file, then run `python bot.py auth-youtube`.
"""

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_credentials(client_secret: Path, token_file: Path, interactive: bool = False) -> Credentials:
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interactive:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        creds = flow.run_local_server(port=0)
    else:
        raise RuntimeError("YouTube is not authorised yet. Run: python bot.py auth-youtube")
    token_file.write_text(creds.to_json())
    return creds


def upload(video: Path, script: dict, creds: Credentials, privacy: str,
           category_id: str = "27", synthetic_media: bool = True) -> str:
    youtube = build("youtube", "v3", credentials=creds)

    hashtags = " ".join(f"#{h}" for h in script["hashtags"])
    title = script["title"][:90]
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"

    body = {
        "snippet": {
            "title": title[:100],
            "description": f"{script['description']}\n\n{hashtags} #Shorts",
            "tags": script["hashtags"],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": synthetic_media,
        },
    }

    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("YouTube upload %d%%", int(status.progress() * 100))

    video_id = response["id"]
    log.info("YouTube upload done: https://youtube.com/shorts/%s", video_id)
    return video_id
