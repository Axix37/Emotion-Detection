"""
Asks Claude for a short-form video script and returns it as a dict.

Output shape:
{
  "title": str, "description": str, "hashtags": [str],
  "hook": str,
  "scenes": [{"narration": str, "on_screen_text": str}, ...]
}
"""

import json
import logging

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "hook": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "on_screen_text": {"type": "string"},
                },
                "required": ["narration", "on_screen_text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "description", "hashtags", "hook", "scenes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You write scripts for vertical short-form videos (YouTube Shorts / TikTok).

Goals: stop the scroll in the first second, deliver real value, and make people want to \
watch to the end and follow. Every claim must be accurate. Do not invent statistics, \
quotes, or events. If you are not confident a fact is true, leave it out.

Format rules:
- "hook": one punchy spoken sentence (under 12 words) that opens the video.
- "scenes": 5 to 7 scenes. Each "narration" is 1-2 short spoken sentences (under 30 words). \
"on_screen_text" is a 2-7 word caption summarising that scene. No emojis in narration.
- The last scene ends with a short call to follow for more.
- Total narration (hook + scenes) should take 35-55 seconds to read aloud.
- "title": under 70 characters, curiosity-driven but not misleading clickbait.
- "description": 1-3 sentences.
- "hashtags": 3-6 relevant hashtags without the # symbol."""


def write_script(niche: str, recent_titles: list[str], extra_instructions: str = "") -> dict:
    client = anthropic.Anthropic()

    avoid = "\n".join(f"- {t}" for t in recent_titles[-50:]) or "(none yet)"
    user_msg = (
        f"Channel niche: {niche}\n\n"
        f"Pick a fresh topic within this niche and write one video script. "
        f"Do not repeat or closely resemble these previous videos:\n{avoid}"
    )
    if extra_instructions:
        user_msg += f"\n\nAdditional instructions from the channel owner:\n{extra_instructions}"

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA},
        },
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to write this script: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Script response was cut off (max_tokens).")

    text = "".join(b.text for b in response.content if b.type == "text")
    script = json.loads(text)
    if not script["scenes"]:
        raise RuntimeError("Claude returned a script with no scenes.")
    script["hashtags"] = [h.lstrip("#").replace(" ", "") for h in script["hashtags"]]
    log.info("Script written: %s (%d scenes)", script["title"], len(script["scenes"]))
    return script
