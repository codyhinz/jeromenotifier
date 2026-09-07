#!/usr/bin/env python3
"""NoHitJerome YouTube -> Discord notifier.

Three rules this file is built around:

  1. Never exit non-zero for something the next scheduled run can retry
     (YouTube hiccup, Discord hiccup). The cron schedule is the retry.
  2. Never mark a video seen unless its Discord post actually succeeded,
     and write that fact to disk immediately, one video at a time.
  3. Never throw state away. If state.json is unparseable, salvage what
     ids we can from it, then fall back to git history. Seeding a fresh
     empty state is the last resort, because that is what causes reposts.
"""

import json
import os
import re
import subprocess
import sys
import time

import requests

CHANNEL_ID    = "UClSx_2ThsuFxMu-hQvTqkqw"
CHANNEL_NAME  = "NoHitJerome"
STATE_FILE    = "state.json"
KEEP_IDS      = 50   # plenty of headroom over MAX_RESULTS
MAX_RESULTS   = 10
HISTORY_DEPTH = 15   # how far back to look for a good state.json

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

CONFLICT_MARKER = re.compile(r"^(<{7}|={7}|>{7})")


def parse_state(text):
    """Return a list of seen ids, or None if nothing usable is in `text`."""
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("seen_ids"), list):
            return [str(v) for v in data["seen_ids"]]
    except json.JSONDecodeError:
        pass

    # The whole file isn't valid JSON. Scan it line by line and union every
    # id we can find. This rescues a file git left with conflict markers, and
    # a file the `union` merge driver left with two JSON objects stacked up.
    ids, found_any = [], False
    for line in text.splitlines():
        line = line.strip()
        if not line or CONFLICT_MARKER.match(line):
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, dict) and isinstance(chunk.get("seen_ids"), list):
            found_any = True
            for vid in chunk["seen_ids"]:
                vid = str(vid)
                if vid not in ids:
                    ids.append(vid)
    return ids if found_any else None


def state_from_git():
    """Walk back through commits looking for a state.json we can read."""
    for n in range(HISTORY_DEPTH):
        try:
            result = subprocess.run(
                ["git", "show", f"HEAD~{n}:{STATE_FILE}"],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"git unavailable for recovery: {exc}")
            return None
        if result.returncode != 0:
            continue
        ids = parse_state(result.stdout)
        if ids:
            print(f"Recovered {len(ids)} ids from HEAD~{n}.")
            return ids
    return None


def load_state():
    """Best-effort load. Returns a list of ids, or None if truly nothing."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            ids = parse_state(f.read())
        if ids is not None:
            return ids
        print(f"{STATE_FILE} is unreadable — falling back to git history.")
    else:
        print(f"{STATE_FILE} missing — falling back to git history.")
    return state_from_git()


def save_state(ids):
    payload = {"seen_ids": ids[-KEEP_IDS:]}
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
        f.write("\n")
    os.replace(tmp, STATE_FILE)  # atomic, so a crash can't leave a half file


def normalize_state():
    """Rewrite state.json as one clean JSON object. Used after a git rebase."""
    ids = load_state()
    if ids is None:
        print("Nothing to normalize.")
        return 1
    save_state(ids)
    print(f"Normalized state.json ({len(ids[-KEEP_IDS:])} ids).")
    return 0


def get_recent_videos():
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "key":        YOUTUBE_API_KEY,
            "channelId":  CHANNEL_ID,
            "part":       "snippet",
            "order":      "date",
            "maxResults": MAX_RESULTS,
            "type":       "video",
        },
        timeout=15,
    )
    r.raise_for_status()
    videos = []
    for item in r.json().get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        videos.append({
            "id":    video_id,
            "title": item["snippet"]["title"],
            "url":   f"https://www.youtube.com/watch?v={video_id}",
        })
    return videos


def post_to_discord(video):
    """Return True only if Discord definitely accepted the message."""
    message = (
        f"🎥 **{CHANNEL_NAME}** just uploaded a new video!\n"
        f"**{video['title']}**\n{video['url']}"
    )
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                DISCORD_WEBHOOK, json={"content": message}, timeout=15
            )
        except requests.RequestException as exc:
            print(f"Discord attempt {attempt} errored: {exc}")
            time.sleep(3 * attempt)
            continue

        if resp.status_code == 429:
            wait = min(float(resp.headers.get("Retry-After", 5)), 30)
            print(f"Rate limited, waiting {wait}s.")
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            print(f"Discord {resp.status_code} on attempt {attempt}.")
            time.sleep(3 * attempt)
            continue
        if resp.ok:
            return True

        print(f"Discord rejected the post: {resp.status_code} {resp.text[:200]}")
        return False
    return False


def main():
    if "--normalize-state" in sys.argv:
        return normalize_state()

    if not DISCORD_WEBHOOK or not YOUTUBE_API_KEY:
        # Nothing can work without these, and no retry will fix it.
        print("::error::DISCORD_WEBHOOK or YOUTUBE_API_KEY is not set.")
        return 1

    seen = load_state()

    print("Checking YouTube...")
    try:
        videos = get_recent_videos()
    except Exception as exc:
        print(f"YouTube lookup failed ({exc}) — skipping this run, will retry.")
        return 0

    if not videos:
        print("No videos returned.")
        return 0

    if not seen:
        seeded = [v["id"] for v in videos]
        save_state(seeded)
        print(f"No prior state anywhere — seeded {len(seeded)} ids, posting nothing.")
        return 0

    new_videos = [v for v in videos if v["id"] not in seen]
    if not new_videos:
        print("No new videos.")
        save_state(seen)  # rewrites a merged/messy file back to clean JSON
        return 0

    for video in reversed(new_videos):  # oldest first
        if not post_to_discord(video):
            print("Post failed — leaving this and any newer video unseen for next run.")
            break
        seen.append(video["id"])
        save_state(seen)  # persist after EACH success, not at the end
        print(f"Posted: {video['title']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
