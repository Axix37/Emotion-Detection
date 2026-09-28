# Shorts Bot — auto-post AI videos to YouTube Shorts & TikTok

Each run:

1. **Claude** picks a fresh topic in your niche and writes a ~45 s script (hook, 5–7 scenes, title, hashtags). It sees your past titles so it doesn't repeat itself.
2. **Renderer** builds a 1080×1920 video: neural voiceover (edge-tts), big captions, subtitles for sound-off viewers, a progress bar, slow zoom, and optional background music.
3. **Uploaders** post it through the *official* YouTube Data API and TikTok Content Posting API.

Everything is saved under `output/<date>_<title>/` (`script.json`, `video.mp4`) and logged to `output/bot.log`.

---

## Read this first: what it can and can't do

This tool automates the *work*. It doesn't guarantee *income*. Things to know up front:

| | YouTube Shorts | TikTok |
|---|---|---|
| **To get paid** | YouTube Partner Program: 1,000 subscribers **and** 10M Shorts views in 90 days (or 4,000 watch hours). | Creator Rewards: 10,000 followers, 100,000 views in 30 days, and **only videos over 1 minute earn**. |
| **API posting limits** | Uploads from an *unverified* Google API project stay **private** until you pass YouTube's API compliance audit. The default quota allows about 6 uploads per day. | Until TikTok audits your app, posts can only be **private (SELF_ONLY)**. |

- **Low-effort, mass-produced content usually doesn't get monetized.** YouTube's "inauthentic content" policy and TikTok's originality rules reject channels that look templated. Channels that earn pick a narrow niche, review what goes out, and improve on what their analytics show. Treat the bot as a production assistant, not a money printer.
- **Keep it honest.** The prompt tells Claude not to invent facts, and `YOUTUBE_SYNTHETIC_MEDIA=true` discloses AI content. Also turn on TikTok's "AI-generated content" label in the app.
- **Quality beats volume.** One or two good videos a day beats twenty weak ones, and posting too much can get you flagged as spam.
- **Other ways to earn:** affiliate links in the description, a pinned comment pointing to your product, or brand deals once you have an audience. These often pay sooner than ad revenue.

---

## Setup (about 30 minutes, once)

### 1. Install

```bash
cd shorts_bot
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

No separate ffmpeg install is needed; `imageio-ffmpeg` ships one.

### 2. Claude API key

Create a key at <https://console.anthropic.com> and put it in `config.env` as `ANTHROPIC_API_KEY`. Each script costs a few cents.

Set `NICHE` in `config.env`. Be specific: *"weird history of everyday objects"* beats *"facts"*.

### 3. Try it without uploading

```bash
python bot.py generate
```

Watch `output/.../video.mp4`. Adjust `NICHE`, `EXTRA_INSTRUCTIONS`, `VOICE` (list voices with `edge-tts --list-voices`) and add music until you like the result.

For music, put royalty-free `.mp3` files in `shorts_bot/music/`. The YouTube Audio Library is a safe source. Never use copyrighted songs.

### 4. YouTube

1. Go to <https://console.cloud.google.com>, create a project, and enable **YouTube Data API v3**.
2. Under **OAuth consent screen**, choose External and add your own Google account as a *test user*.
3. Under **Credentials**, choose Create credentials → OAuth client ID → **Desktop app**. Download the JSON and save it as `shorts_bot/client_secret.json`.
4. Run `python bot.py auth-youtube`. A browser opens; sign in with the channel's account.
5. To post publicly, apply for the [YouTube API audit](https://support.google.com/youtube/contact/yt_api_form). Until then uploads stay private, and you can make them public by hand in YouTube Studio.

### 5. TikTok

1. At <https://developers.tiktok.com>, create an app. Add the **Login Kit** and **Content Posting API** products, request the `video.publish` scope, and turn on **Direct Post**.
2. Register a redirect URI. It must be HTTPS; any page you control works, even if it shows a 404. Put the client key, client secret and redirect URI in `config.env`.
3. Run `python bot.py auth-tiktok`, open the printed link, approve, then paste the full URL you were redirected to.
4. Posts stay `SELF_ONLY` (private) until TikTok approves your app's audit. After that, set `TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE`.

To post to only one platform, set `PLATFORMS=youtube` (or `tiktok`).

### 6. Post

```bash
python bot.py run
```

---

## Run it automatically

**Windows:** open Task Scheduler → Create Basic Task → Daily → start `run_bot.bat`. Add extra triggers for more posts per day.

**macOS/Linux (cron):** this runs at 9:00 and 18:00 every day:

```
0 9,18 * * *  cd /path/to/shorts_bot && .venv/bin/python bot.py run
```

The computer has to be on at those times. For hands-off posting, run it on a small cloud VM.

---

## Files

| File | Purpose |
|---|---|
| `bot.py` | CLI entry point: `run`, `generate`, `auth-youtube`, `auth-tiktok` |
| `script_writer.py` | Claude prompt and JSON schema for scripts |
| `renderer.py` | Voiceover, frames, and ffmpeg video assembly |
| `youtube_uploader.py` | YouTube Data API upload |
| `tiktok_uploader.py` | TikTok Content Posting API upload |
| `history.json` | Past videos, used to avoid repeat topics (auto-created) |

Secrets (`config.env` values, `client_secret.json`, `*_token.json`) are listed in `.gitignore`. Never commit them.
