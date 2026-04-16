import requests
import os
import json

CHANNEL_ID      = "UClSx_2ThsuFxMu-hQvTqkqw"
CHANNEL_NAME    = "NoHitJerome"
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
STATE_FILE      = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_video_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_latest_video():
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "key":        YOUTUBE_API_KEY,
            "channelId":  CHANNEL_ID,
            "part":       "snippet",
            "order":      "date",
            "maxResults": 1,
            "type":       "video"
        },
        timeout=10
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return None
    item     = items[0]
    video_id = item["id"]["videoId"]
    title    = item["snippet"]["title"]
    url      = f"https://www.youtube.com/watch?v={video_id}"
    return {"id": video_id, "title": title, "url": url}

def post_to_discord(title, url):
    message = f"🎥 **{CHANNEL_NAME}** just uploaded a new video!\n**{title}**\n{url}"
    requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10).raise_for_status()

def main():
    state = load_state()
    print("Checking YouTube...")

    video = get_latest_video()
    if not video:
        print("No videos found.")
        return

    print(f"Latest video: {video['title']} (ID: {video['id']})")
    print(f"Last seen ID: {state['last_video_id']}")

    if video["id"] != state["last_video_id"]:
        if state["last_video_id"] is None:
            print("First run — saving video ID without posting.")
        else:
            print("New video detected — posting to Discord!")
            post_to_discord(video["title"], video["url"])
        state["last_video_id"] = video["id"]
    else:
        print("No new video.")

    save_state(state)

if __name__ == "__main__":
    main()
