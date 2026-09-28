"""
Turns a script dict into a 1080x1920 MP4 with voiceover, captions and optional music.

Uses edge-tts for the voice and the ffmpeg binary bundled with imageio-ffmpeg,
so nothing has to be installed system-wide.
"""

import asyncio
import hashlib
import logging
import os
import random
import re
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

WIDTH, HEIGHT, FPS = 1080, 1920, 30
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

PALETTES = [
    ((15, 32, 67), (88, 28, 135)),
    ((12, 74, 110), (6, 95, 70)),
    ((69, 10, 10), (124, 45, 18)),
    ((17, 24, 39), (55, 65, 81)),
    ((49, 46, 129), (157, 23, 77)),
    ((20, 83, 45), (21, 94, 117)),
]

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    custom = os.getenv("FONT_PATH")
    for path in ([custom] if custom else []) + FONT_CANDIDATES:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    log.warning("No TTF font found; set FONT_PATH in config.env for better captions.")
    return ImageFont.load_default(size)


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-2000:]}")
    return proc.stderr


def _duration(path: Path) -> float:
    proc = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not m:
        raise RuntimeError(f"Could not read duration of {path}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------

def synthesize(text: str, out_path: Path, voice: str, rate: str) -> None:
    async def _go():
        await edge_tts.Communicate(text, voice, rate=rate).save(str(out_path))

    asyncio.run(_go())
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"TTS produced no audio for: {text[:60]}")


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_frame(caption: str, subtitle: str, background: Image.Image,
                 index: int, total: int, out_path: Path) -> None:
    img = background.copy()
    draw = ImageDraw.Draw(img)
    max_w = WIDTH - 160

    # Shrink the caption font until it fits in at most 5 lines.
    size = 120
    while True:
        font = _font(size)
        lines = _wrap(draw, caption.upper(), font, max_w)
        if len(lines) <= 5 or size <= 60:
            break
        size -= 8

    line_h = int(size * 1.2)
    block_h = line_h * len(lines)
    y = int(HEIGHT * 0.40) - block_h // 2

    pad = 50
    widest = max(draw.textlength(l, font=font) for l in lines)
    box = [(WIDTH - widest) / 2 - pad, y - pad, (WIDTH + widest) / 2 + pad, y + block_h + pad]
    draw.rounded_rectangle(box, radius=40, fill=(0, 0, 0))

    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((WIDTH - w) / 2, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    # Smaller subtitle (the narration) under the caption, for sound-off viewers.
    sub_font = _font(52)
    sy = int(box[3]) + 90
    for line in _wrap(draw, subtitle, sub_font, max_w)[:6]:
        w = draw.textlength(line, font=sub_font)
        draw.text(((WIDTH - w) / 2, sy), line, font=sub_font, fill=(235, 235, 235),
                  stroke_width=3, stroke_fill=(0, 0, 0))
        sy += 66

    # Progress bar keeps people watching to the end.
    bar_y = HEIGHT - 260
    draw.rounded_rectangle([80, bar_y, WIDTH - 80, bar_y + 16], radius=8, fill=(90, 90, 90))
    filled = 80 + (WIDTH - 160) * (index + 1) / total
    draw.rounded_rectangle([80, bar_y, filled, bar_y + 16], radius=8, fill=(250, 204, 21))

    img.save(out_path)


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------

def _segment(image: Path, audio: Path, out: Path) -> None:
    seconds = _duration(audio) + 0.25
    frames = int(seconds * FPS)
    # Slow push-in so the frame is never completely static.
    zoom = f"zoompan=z='min(zoom+0.0006,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    _run([
        FFMPEG, "-y", "-loop", "1", "-i", str(image), "-i", str(audio),
        "-filter_complex", f"[0:v]{zoom},format=yuv420p[v];[1:a]apad,aresample=44100[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{seconds:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ac", "2", str(out),
    ])


def _pick_music(music_dir: Path) -> Path | None:
    if not music_dir.is_dir():
        return None
    tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in {".mp3", ".wav", ".m4a"}]
    return random.choice(tracks) if tracks else None


def render_video(script: dict, work_dir: Path, out_path: Path, voice: str,
                 rate: str = "+8%", music_dir: Path | None = None,
                 music_volume: float = 0.12) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)

    segments = [{"narration": script["hook"], "on_screen_text": script["title"]}] + script["scenes"]
    seed = int(hashlib.md5(script["title"].encode()).hexdigest(), 16)
    background = _gradient(*PALETTES[seed % len(PALETTES)])

    parts = []
    for i, seg in enumerate(segments):
        audio = work_dir / f"seg{i:02d}.mp3"
        image = work_dir / f"seg{i:02d}.png"
        clip = work_dir / f"seg{i:02d}.mp4"
        synthesize(seg["narration"], audio, voice, rate)
        render_frame(seg["on_screen_text"], seg["narration"], background, i, len(segments), image)
        _segment(image, audio, clip)
        parts.append(clip)
        log.info("Rendered segment %d/%d", i + 1, len(segments))

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    joined = work_dir / "joined.mp4"
    _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(joined)])

    music = _pick_music(music_dir) if music_dir else None
    if music:
        _run([
            FFMPEG, "-y", "-i", str(joined), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            f"[1:a]volume={music_volume}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-shortest", str(out_path),
        ])
    else:
        joined.replace(out_path)

    log.info("Video ready: %s (%.1fs)", out_path, _duration(out_path))
    return out_path
