"""
Posts a video to TikTok via the official Content Posting API (Direct Post).

Requires a TikTok developer app with the `video.publish` scope and a user access token
(see README). Until TikTok audits your app, posts can only be SELF_ONLY (private).
"""

import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API = "https://open.tiktokapis.com/v2"


class TikTokClient:
    def __init__(self, client_key: str, client_secret: str, token_file: Path):
        self.client_key = client_key
        self.client_secret = client_secret
        self.token_file = token_file
        if not token_file.exists():
            raise RuntimeError(f"TikTok token file not found: {token_file} (see README)")
        self.tokens = json.loads(token_file.read_text())

    # -- auth ---------------------------------------------------------------

    def refresh(self) -> None:
        resp = requests.post(
            f"{API}/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.tokens["refresh_token"],
            },
            timeout=30,
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"TikTok token refresh failed: {data}")
        self.tokens.update(data)
        self.token_file.write_text(json.dumps(self.tokens, indent=2))
        log.info("TikTok access token refreshed")

    def _post(self, path: str, body: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.tokens['access_token']}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        resp = requests.post(f"{API}{path}", headers=headers, json=body, timeout=60)
        data = resp.json()
        code = data.get("error", {}).get("code", "ok")
        if code == "access_token_invalid":
            self.refresh()
            return self._post(path, body)
        if code != "ok":
            raise RuntimeError(f"TikTok API error on {path}: {data['error']}")
        return data["data"]

    # -- posting ------------------------------------------------------------

    def upload(self, video: Path, script: dict, privacy: str) -> str:
        creator = self._post("/post/publish/creator_info/query/", {})
        allowed = creator.get("privacy_level_options", [])
        if privacy not in allowed:
            log.warning("TikTok privacy %s not allowed for this account/app; using %s",
                        privacy, allowed[0] if allowed else "SELF_ONLY")
            privacy = allowed[0] if allowed else "SELF_ONLY"

        hashtags = " ".join(f"#{h}" for h in script["hashtags"])
        caption = f"{script['title']} {hashtags}"[:2200]
        size = video.stat().st_size

        init = self._post("/post/publish/video/init/", {
            "post_info": {
                "title": caption,
                "privacy_level": privacy,
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            # Shorts are well under 64 MB, so a single chunk is allowed.
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        })

        with open(video, "rb") as f:
            resp = requests.put(
                init["upload_url"],
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(size),
                    "Content-Range": f"bytes 0-{size - 1}/{size}",
                },
                data=f,
                timeout=300,
            )
        resp.raise_for_status()

        publish_id = init["publish_id"]
        for _ in range(60):
            status = self._post("/post/publish/status/fetch/", {"publish_id": publish_id})
            state = status.get("status")
            if state == "PUBLISH_COMPLETE":
                log.info("TikTok post published (publish_id=%s)", publish_id)
                return publish_id
            if state == "FAILED":
                raise RuntimeError(f"TikTok publish failed: {status.get('fail_reason')}")
            time.sleep(5)
        log.warning("TikTok still processing after 5 min (publish_id=%s)", publish_id)
        return publish_id
