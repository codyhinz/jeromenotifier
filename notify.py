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
    return {"seen_ids": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_latest_videos():
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "key":        YOUTUBE_API_KEY,
            "channelId":  CHANNEL_ID,
            "part":       "snippet",
            "order":      "date",
            "maxResults": 5,
            "type":       "video"
        },
        timeout=10
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    videos = []
    for item in items:
        video_id = item["id"]["videoId"]
        title    = item["snippet"]["title"]
        url      = f"https://www.youtube.com/watch?v={video_id}"
        videos.append({"id": video_id, "title": title, "url": url})
    return videos

def post_to_discord(title, url):
    message = f"🎥 **{CHANNEL_NAME}** just uploaded a new video!\n**{title}**\n{url}"
    requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10).raise_for_status()

def main():
    state    = load_state()
    seen_ids = state.get("seen_ids", [])

    print("Checking YouTube...")
    videos = get_latest_videos()

    if not videos:
        print("No videos found.")
        return

    # First run — just save all current IDs without posting
    if not seen_ids:
        seen_ids = [v["id"] for v in videos]
        print(f"First run — saving {len(seen_ids)} video IDs without posting.")
        state["seen_ids"] = seen_ids
        save_state(state)
        return

    # Find any videos we haven't seen before
    new_videos = [v for v in videos if v["id"] not in seen_ids]

    if new_videos:
        for video in reversed(new_videos):  # Post oldest new video first
            print(f"New video detected: {video['title']} — posting to Discord!")
            post_to_discord(video["title"], video["url"])
        # Update seen IDs, keep last 20 to avoid the list growing forever
        all_ids = seen_ids + [v["id"] for v in new_videos]
        state["seen_ids"] = all_ids[-20:]
    else:
        print("No new videos.")

    save_state(state)

if __name__ == "__main__":
    main()
