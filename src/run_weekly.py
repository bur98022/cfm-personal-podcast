import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dateutil import tz

# Ensure this repo root is on the Python path so imports work in GitHub Actions.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cfm_fetch import fetch_cfm_week_text
from src.script_writer import load_master_prompt, build_prompt, generate_scripts
from src.tts import tts_to_mp3
from src.drive_upload import get_drive_service, find_or_create_folder, upload_text, upload_bytes


def load_index(path: str = "cfm_index/cfm_2026_index.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_week_dates(start_date: str, end_date: str) -> str:
    return f"{start_date} to {end_date}"

def main():
    # Required env vars
    openai_key = os.getenv("OPENAI_API_KEY")
    drive_folder_id = os.getenv("GDRIVE_FOLDER_ID")
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    missing = [k for k, v in [
        ("OPENAI_API_KEY", openai_key),
        ("GDRIVE_FOLDER_ID", drive_folder_id),
        ("GOOGLE_SERVICE_ACCOUNT_JSON", sa_json),
    ] if not v]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    # Load index and pick Week 1 for prototype
    index = load_index()
    week = index[0]  # Prototype: Week 1
    week_num = int(week["week"])
    week_title = week["title"]
    week_dates = parse_week_dates(week["start_date"], week["end_date"])
    scripture_blocks = week.get("scripture_blocks", "")
    url = week["url"]

    print(f"Generating Week {week_num}: {week_title}")
    print(f"Fetching: {url}")

    cfm_text = fetch_cfm_week_text(url)

    master = load_master_prompt()
    prompt = build_prompt(
        master=master,
        week_title=f"Week {week_num}: {week_title}",
        week_dates=week_dates,
        scripture_blocks=scripture_blocks,
        cfm_text=cfm_text,
    )

    print("Generating scripts...")
    scripts_text = generate_scripts(prompt=prompt, model="gpt-4o-mini")

    # Prepare Drive folders
    service = get_drive_service(sa_json)
    year_folder_name = "2026 Old Testament"
    week_folder_name = f"Week {week_num:02d} - {week_title}"

    year_folder_id = find_or_create_folder(service, year_folder_name, drive_folder_id)
    week_folder_id = find_or_create_folder(service, week_folder_name, year_folder_id)
    scripts_folder_id = find_or_create_folder(service, "scripts", week_folder_id)
    audio_folder_id = find_or_create_folder(service, "audio", week_folder_id)

    # Upload combined scripts
    upload_text(service, scripts_folder_id, "all_episodes.txt", scripts_text)

    # Split into 5 episodes (simple heuristic: look for "Episode 1)" etc.)
    # If the model output varies, we still have all_episodes.txt as the source of truth.
    episodes = []
    current = []
    for line in scripts_text.splitlines():
        if line.strip().lower().startswith("episode 1") or line.strip().lower().startswith("1) big picture"):
            if current:
                episodes.append("\n".join(current).strip())
                current = []
        current.append(line)
    if current:
        episodes.append("\n".join(current).strip())

    # If heuristic fails, just TTS the whole thing into one file (still useful)
    if len(episodes) < 5:
        episodes = [scripts_text]

    print(f"Creating MP3s ({len(episodes)} file(s))...")
    voice = "cedar"  # single consistent voice
    for i, ep_text in enumerate(episodes[:5], start=1):
        mp3 = tts_to_mp3(ep_text, voice=voice, model="gpt-4o-mini-tts")
        filename = f"W{week_num:02d}_E{i:02d}.mp3"
        upload_bytes(service, audio_folder_id, filename, mp3, mime_type="audio/mpeg")
        print(f"Uploaded {filename}")

    print("Done. Check your Google Drive folder.")

if __name__ == "__main__":
    main()
