import json
import os
import sys
from pathlib import Path

# Ensure repo root is importable when running as a script (GitHub Actions)
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cfm_fetch import fetch_cfm_week_text
from src.script_writer import (
    load_master_prompt,
    build_prompt,
    generate_scripts,
    shorten_to_word_range,
    word_count,
)
from src.tts import tts_to_mp3
from src.drive_upload import get_drive_service_oauth, find_or_create_folder, upload_text, upload_bytes

def load_index(path: str = "cfm_index/cfm_2026_index.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_week_dates(start_date: str, end_date: str) -> str:
    return f"{start_date} to {end_date}"

def split_episodes(all_text: str) -> list[str]:
    """
    Split by the exact headers we defined in the master prompt.
    Returns up to 4 episode strings.
    """
    headers = [
        "=== EPISODE 1: BIG PICTURE & CONTEXT ===",
        "=== EPISODE 2: SCRIPTURE WALKTHROUGH ===",
        "=== EPISODE 3: DOCTRINES & PRINCIPLES ===",
        "=== EPISODE 4: MODERN LIFE APPLICATION ===",
    ]

    # Find each header position
    positions = []
    for h in headers:
        idx = all_text.find(h)
        if idx != -1:
            positions.append((idx, h))
    positions.sort()

    if len(positions) < 2:
        return []

    chunks = []
    for i in range(len(positions)):
        start = positions[i][0]
        end = positions[i + 1][0] if i + 1 < len(positions) else len(all_text)
        chunks.append(all_text[start:end].strip())

    return chunks[:4]

def main():
    # Required env vars
    openai_key = os.getenv("OPENAI_API_KEY")
    drive_folder_id = os.getenv("GDRIVE_FOLDER_ID")
    
    missing = [k for k, v in [
        ("OPENAI_API_KEY", openai_key),
        ("GDRIVE_FOLDER_ID", drive_folder_id),
            ] if not v]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")

    # Load index and pick Week 1 for now
    index = load_index()
    week = index[0]
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

    print("Generating scripts (4 episodes)...")
    scripts_text = generate_scripts(prompt=prompt, model="gpt-4o-mini")

    # Prepare Drive folders
    service = get_drive_service_oauth()
    year_folder_name = "2026 Old Testament"
    week_folder_name = f"Week {week_num:02d} - {week_title}"

    year_folder_id = find_or_create_folder(service, year_folder_name, drive_folder_id)
    week_folder_id = find_or_create_folder(service, week_folder_name, year_folder_id)
    scripts_folder_id = find_or_create_folder(service, "scripts", week_folder_id)
    audio_folder_id = find_or_create_folder(service, "audio", week_folder_id)

    # Upload combined scripts
    upload_text(service, scripts_folder_id, "all_episodes.txt", scripts_text)

    episodes = split_episodes(scripts_text)
    if len(episodes) != 4:
        # Failsafe: still upload combined scripts; stop before TTS to avoid garbage audio
        raise SystemExit(
            "Could not reliably split into 4 episodes. "
            "Check scripts/all_episodes.txt in Drive and we’ll adjust the prompt/splitter."
        )

    # Enforce 10-min-ish length
    MIN_WORDS = 1300
    MAX_WORDS = 1600

    print("Creating MP3s (4 episodes, ~10 min each)...")
    voice = "alloy"
    tts_model = "tts-1"

    for i, ep_text in enumerate(episodes, start=1):
        wc = word_count(ep_text)
        print(f"Episode {i} word count: {wc}")

        if wc > MAX_WORDS:
            print(f"Episode {i} too long; shortening to {MIN_WORDS}-{MAX_WORDS} words...")
            ep_text = shorten_to_word_range(ep_text, MIN_WORDS, MAX_WORDS, model="gpt-4o-mini")
            wc2 = word_count(ep_text)
            print(f"Episode {i} new word count: {wc2}")

        # Save final episode script
        script_name = f"W{week_num:02d}_E{i:02d}.txt"
        upload_text(service, scripts_folder_id, script_name, ep_text)

        # TTS
        mp3 = tts_to_mp3(ep_text, voice=voice, model=tts_model)
        audio_name = f"W{week_num:02d}_E{i:02d}.mp3"
        upload_bytes(service, audio_folder_id, audio_name, mp3, mime_type="audio/mpeg")
        print(f"Uploaded {audio_name}")

    print("Done. Check your Google Drive folder.")

if __name__ == "__main__":
    main()
