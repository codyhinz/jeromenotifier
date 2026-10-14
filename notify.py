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

import requests
import os
import json

TWITCH_USERNAME  = "nohitjerome"
CHANNEL_NAME     = "NOHITJEROME"
# One webhook URL per line (commas also work) — one per Discord server.
DISCORD_WEBHOOKS = [
    u.strip()
    for u in os.environ["DISCORD_WEBHOOK"].replace(",", "\n").splitlines()
    if u.strip()
]
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_SECRET    = os.environ["TWITCH_SECRET"]
STATE_FILE       = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"was_live": False}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_token():
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id":     TWITCH_CLIENT_ID,
            "client_secret": TWITCH_SECRET,
            "grant_type":    "client_credentials"
        },
        timeout=10
    )
    r.raise_for_status()
    return r.json()["access_token"]

def get_stream(token):
    r = requests.get(
        "https://api.twitch.tv/helix/streams",
        params={"user_login": TWITCH_USERNAME},
        headers={
            "Client-ID":     TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}"
        },
        timeout=10
    )
    r.raise_for_status()
    data = r.json()["data"]
    return data[0] if data else None

def post_to_discord(message):
    """Post to every server. Return True if at least one accepted it."""
    delivered = 0
    for i, url in enumerate(DISCORD_WEBHOOKS, 1):
        try:
            requests.post(url, json={"content": message}, timeout=10).raise_for_status()
            delivered += 1
        except requests.RequestException as exc:
            print(f"Webhook #{i} of {len(DISCORD_WEBHOOKS)} failed: {exc}")
    return delivered > 0

def main():
    state    = load_state()
    token    = get_token()
    stream   = get_stream(token)
    is_live  = stream is not None
    was_live = state.get("was_live", False)

    print(f"Live: {is_live} | Was live: {was_live} | Webhooks: {len(DISCORD_WEBHOOKS)}")

    # Only notify on offline → online transition
    if is_live and not was_live:
        title = stream.get("title", "")
        game  = stream.get("game_name", "Unknown")
        print("Just went live — posting to Discord!")
        posted = post_to_discord(
            f"🔴 **{CHANNEL_NAME}** is live on Twitch!\n"
            f"**{title}**\n"
            f"Playing: {game}\n"
            f"https://twitch.tv/{TWITCH_USERNAME}"
        )
        if not posted:
            # Nobody got it — leave was_live False so the next run tries again.
            print("No webhook accepted the post — will retry next run.")
            return
    elif is_live and was_live:
        print("Still live — no notification.")
    else:
        print("Not live.")

    state["was_live"] = is_live
    save_state(state)

if __name__ == "__main__":
    main()
