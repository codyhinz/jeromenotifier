import requests
from datetime import datetime, timezone, timedelta
import os

CHANNEL_ID      = "UClSx_2ThsuFxMu-hQvTqkqw"
CHANNEL_NAME    = "NoHitJerome"
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
CHECK_MINUTES   = 25  # Slightly over 20 to avoid missing videos on the edge

def get_latest_video():
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key":        YOUTUBE_API_KEY,
        "channelId":  CHANNEL_ID,
        "part":       "snippet",
        "order":      "date",
        "maxResults": 1,
        "type":       "video"
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        return None
    item      = items[0]
    video_id  = item["id"]["videoId"]
    title     = item["snippet"]["title"]
    published = item["snippet"]["publishedAt"]  # e.g. "2025-04-15T18:00:00Z"
    pub_time  = datetime.fromisoformat(published.replace("Z", "+00:00"))
    url       = f"https://www.youtube.com/watch?v={video_id}"
    return {"title": title, "url": url, "published": pub_time}

def post_to_discord(title, url):
    message = f"🎥 **{CHANNEL_NAME}** just uploaded a new video!\n**{title}**\n{url}"
    requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10).raise_for_status()

def main():
    print("Checking YouTube...")
    video = get_latest_video()
    if not video:
        print("No videos found.")
        return

    now = datetime.now(timezone.utc)
    age = now - video["published"]
    print(f"Latest video: {video['title']} (published {video['published']})")

    if age < timedelta(minutes=CHECK_MINUTES):
        print("New video detected — posting to Discord!")
        post_to_discord(video["title"], video["url"])
    else:
        print("No new video in the last 25 minutes.")

if __name__ == "__main__":
    main()
