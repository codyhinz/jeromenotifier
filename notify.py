import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import os
import json

# ── Config ────────────────────────────────────────────────────────────────────
YOUTUBE_RSS      = "https://www.youtube.com/feeds/videos.xml?channel_id=UClSx_2ThsuFxMu-hQvTqkqw"
TWITCH_USERNAME  = "nohitjerome"
CHANNEL_NAME     = "NoHitJerome"
DISCORD_WEBHOOK  = os.environ["DISCORD_WEBHOOK"]
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_SECRET    = os.environ["TWITCH_SECRET"]
STATE_FILE       = "state.json"
CHECK_MINUTES    = 20  # Should match cron interval

# ── State helpers ─────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"twitch_was_live": False, "twitch_stream_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ── Discord ───────────────────────────────────────────────────────────────────
def post_to_discord(message):
    response = requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
    response.raise_for_status()

# ── YouTube ───────────────────────────────────────────────────────────────────
def check_youtube():
    print("Checking YouTube...")
    response = requests.get(
        YOUTUBE_RSS,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        timeout=10
    )
    response.raise_for_status()

    ns = {
        "atom":  "http://www.w3.org/2005/Atom",
        "yt":    "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/"
    }
    root  = ET.fromstring(response.text)
    entry = root.find("atom:entry", ns)
    if entry is None:
        print("No YouTube videos found.")
        return

    title     = entry.find("atom:title", ns).text
    url       = entry.find("atom:link", ns).attrib["href"]
    published = entry.find("atom:published", ns).text
    pub_time  = datetime.fromisoformat(published)
    now       = datetime.now(timezone.utc)

    print(f"Latest video: {title} (published {pub_time})")

    if now - pub_time < timedelta(minutes=CHECK_MINUTES):
        print("New video detected — posting to Discord!")
        post_to_discord(
            f"🎥 **{CHANNEL_NAME}** just uploaded a new video!\n**{title}**\n{url}"
        )
    else:
        print("No new YouTube video.")

# ── Twitch ────────────────────────────────────────────────────────────────────
def get_twitch_token():
    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id":     TWITCH_CLIENT_ID,
            "client_secret": TWITCH_SECRET,
            "grant_type":    "client_credentials"
        },
        timeout=10
    )
    response.raise_for_status()
    return response.json()["access_token"]

def get_stream_info(token):
    response = requests.get(
        "https://api.twitch.tv/helix/streams",
        params={"user_login": TWITCH_USERNAME},
        headers={
            "Client-ID":     TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}"
        },
        timeout=10
    )
    response.raise_for_status()
    data = response.json()["data"]
    return data[0] if data else None

def check_twitch(state):
    print("Checking Twitch...")
    token  = get_twitch_token()
    stream = get_stream_info(token)

    is_live     = stream is not None
    was_live    = state.get("twitch_was_live", False)
    last_stream = state.get("twitch_stream_id")
    current_id  = stream["id"] if stream else None

    print(f"Twitch live: {is_live} | Was live: {was_live} | Stream ID: {current_id}")

    # Only notify when transitioning offline → online (or brand new stream ID)
    if is_live and (not was_live or current_id != last_stream):
        game  = stream.get("game_name", "Unknown game")
        title = stream.get("title", "")
        print("Stream just went live — posting to Discord!")
        post_to_discord(
            f"🔴 **{CHANNEL_NAME}** is live on Twitch!\n"
            f"**{title}**\n"
            f"Playing: {game}\n"
            f"https://twitch.tv/{TWITCH_USERNAME}"
        )

    state["twitch_was_live"]  = is_live
    state["twitch_stream_id"] = current_id
    return state

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    state = load_state()
    check_youtube()
    state = check_twitch(state)
    save_state(state)
    print("Done.")

if __name__ == "__main__":
    main()
