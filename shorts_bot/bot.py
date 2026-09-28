"""
Faceless Shorts bot: Claude writes a script -> video is rendered -> posted to YouTube Shorts and TikTok.

Usage:
    python bot.py run            # make one video and post it to the enabled platforms
    python bot.py generate       # make one video only (no upload) - use this to review quality
    python bot.py auth-youtube   # one-time Google sign-in
    python bot.py auth-tiktok    # one-time TikTok sign-in

Config is loaded from config.env in the same directory.
"""

import argparse
import json
import logging
import os
import re
import secrets
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / "config.env")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR") or SCRIPT_DIR / "output")
HISTORY_FILE = SCRIPT_DIR / "history.json"
YT_CLIENT_SECRET = SCRIPT_DIR / "client_secret.json"
YT_TOKEN = SCRIPT_DIR / "youtube_token.json"
TT_TOKEN = SCRIPT_DIR / "tiktok_token.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler(OUTPUT_DIR / "bot.log", encoding="utf-8")],
)
log = logging.getLogger("shorts_bot")


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def load_history() -> list[dict]:
    return json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []


def save_history(history: list[dict]) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def make_video() -> tuple[dict, Path]:
    from renderer import render_video
    from script_writer import write_script

    niche = env("NICHE")
    if not niche:
        sys.exit("Set NICHE in config.env (e.g. 'surprising science facts').")

    history = load_history()
    script = write_script(niche, [h["title"] for h in history], env("EXTRA_INSTRUCTIONS"))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = OUTPUT_DIR / f"{stamp}_{slugify(script['title'])}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "script.json").write_text(json.dumps(script, indent=2))

    video = render_video(
        script,
        work_dir=folder / "work",
        out_path=folder / "video.mp4",
        voice=env("VOICE", "en-US-AndrewMultilingualNeural"),
        rate=env("VOICE_RATE", "+8%"),
        music_dir=SCRIPT_DIR / "music",
        music_volume=float(env("MUSIC_VOLUME", "0.12")),
    )
    return script, video


def cmd_generate(_args) -> None:
    script, video = make_video()
    log.info("Generated (not uploaded): %s", video)


def cmd_run(_args) -> None:
    platforms = {p.strip().lower() for p in env("PLATFORMS", "youtube,tiktok").split(",") if p.strip()}
    script, video = make_video()
    record = {"title": script["title"], "created": datetime.now().isoformat(), "file": str(video)}
    failures = []

    if "youtube" in platforms:
        try:
            import youtube_uploader
            creds = youtube_uploader.get_credentials(YT_CLIENT_SECRET, YT_TOKEN)
            record["youtube_id"] = youtube_uploader.upload(
                video, script, creds,
                privacy=env("YOUTUBE_PRIVACY", "private"),
                category_id=env("YOUTUBE_CATEGORY_ID", "27"),
                synthetic_media=env("YOUTUBE_SYNTHETIC_MEDIA", "true").lower() == "true",
            )
        except Exception as exc:
            log.exception("YouTube upload failed")
            failures.append(f"youtube: {exc}")

    if "tiktok" in platforms:
        try:
            from tiktok_uploader import TikTokClient
            client = TikTokClient(env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET"), TT_TOKEN)
            record["tiktok_publish_id"] = client.upload(video, script, env("TIKTOK_PRIVACY", "SELF_ONLY"))
        except Exception as exc:
            log.exception("TikTok upload failed")
            failures.append(f"tiktok: {exc}")

    history = load_history()
    history.append(record)
    save_history(history)

    if failures:
        log.error("Finished with errors: %s", "; ".join(failures))
        sys.exit(1)
    log.info("All done: %s", script["title"])


def cmd_auth_youtube(_args) -> None:
    import youtube_uploader
    if not YT_CLIENT_SECRET.exists():
        sys.exit(f"Put your Google OAuth client file at {YT_CLIENT_SECRET} first (see README).")
    youtube_uploader.get_credentials(YT_CLIENT_SECRET, YT_TOKEN, interactive=True)
    log.info("YouTube authorised. Token saved to %s", YT_TOKEN)


def cmd_auth_tiktok(_args) -> None:
    key, secret, redirect = env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET"), env("TIKTOK_REDIRECT_URI")
    if not (key and secret and redirect):
        sys.exit("Set TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REDIRECT_URI in config.env first.")

    state = secrets.token_urlsafe(16)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key,
        "scope": "user.info.basic,video.publish",
        "response_type": "code",
        "redirect_uri": redirect,
        "state": state,
    })
    print(f"\n1. Open this URL and approve access:\n\n{url}\n")
    print("2. You'll be redirected to your redirect URI. Copy the FULL address from the browser bar.")
    pasted = input("\nPaste it here: ").strip()

    query = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
    if query.get("state", [None])[0] != state:
        sys.exit("State mismatch - please start again.")
    code = query["code"][0]

    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_key": key, "client_secret": secret, "code": code,
              "grant_type": "authorization_code", "redirect_uri": redirect},
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        sys.exit(f"TikTok token exchange failed: {data}")
    TT_TOKEN.write_text(json.dumps(data, indent=2))
    log.info("TikTok authorised. Token saved to %s", TT_TOKEN)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run").set_defaults(func=cmd_run)
    sub.add_parser("generate").set_defaults(func=cmd_generate)
    sub.add_parser("auth-youtube").set_defaults(func=cmd_auth_youtube)
    sub.add_parser("auth-tiktok").set_defaults(func=cmd_auth_tiktok)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
