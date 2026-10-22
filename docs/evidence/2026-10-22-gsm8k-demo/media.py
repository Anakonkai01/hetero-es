"""Replay page and video of a saved run (the records `snapshot.py` wrote):

    python media.py <records dir name> [--video]

Writes media/<name>-replay.html (self-contained, plays in any browser) and, with --video, media/<name>.mp4 (needs ffmpeg).
"""

import json
import shutil
import sys
from pathlib import Path

from heteroes.demo import gsm8k
from heteroes.demo.dashboard import render_video
from heteroes.demo.replay_page import recording, write_page
from heteroes.demo.state import replay_frames

FFMPEG = shutil.which("ffmpeg") or str(Path.home() / "miniforge3/envs/ai/bin/ffmpeg")


def main():
    name = sys.argv[1]
    records = gsm8k.EVIDENCE / name
    media = gsm8k.EVIDENCE / "media"
    media.mkdir(exist_ok=True)
    timeline = json.loads((records / "timeline.json").read_text())
    events = json.loads((records / "events.json").read_text())
    title = timeline["experiment"].get("name")
    print(write_page(recording(timeline, events, gsm8k.NAMES, "5070ti-nhan", title), media / f"{name}-replay.html"))
    if "--video" in sys.argv:
        frames = replay_frames(timeline, events, gsm8k.NAMES, steps=240)
        print(render_video(frames, mp4=str(media / f"{name}.mp4"), fps=12, coordinator="5070ti-nhan", ffmpeg=FFMPEG))


if __name__ == "__main__":
    main()
