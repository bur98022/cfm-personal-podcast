import json
import os
import sys
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------
# Ensure repo root is importable (critical for GitHub Actions)
# ---------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------
# Imports from our project
# ---------------------------------------------------------------------
from src.cfm_fetch import fetch_cfm_week_text
from src.script_writer import (
    load_master_prompt,
    build_prompt,
    generate_scripts,
    expand_to_word_range,
    shorten_to_word_range,
    word_count,
)
from src.tts import tts_to_mp3
from src.drive_upload import (
    get_drive_service_oauth,
    find_or_create_folder,
    upload_text,
    upload_bytes,
)

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def load_index(path: str = "cfm_index/cfm_2026_index.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_week_dates(start_date: str, end_date: str) -> str:
    return f"{start_date} to {end_date}"

def split_episodes(all_text: str) -> List[str]:
    headers = [
        "=== EPISODE 1: BIG PICTURE & CONTEXT ===",
        "=== EPISODE 2: SCRIPTURE WALKTHROUGH ===",
        "=== EPISODE 3: DOCTRINES & PRINCIPLES ===",
        "=== EPISODE 4: MODERN LIFE APPLICATION ===",
    ]

    positions = []
    for h in headers:
        idx = all_text.find(h)
        if idx != -1:
            positions.append(idx)

    if len(positions) != 4:
        return []

    positions.append(len(all_text))

    chunks = []
    for i in range(4):
        chunks.append(all_text[positions[i]:positions[i + 1]].strip())

    return chunks

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main() -> None:
    # -------------------------------
    # Validate environment
    # -------------------------------
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY")

    drive_root_id = os.getenv("GDRIVE_FOLDER_ID")
    if not drive_root_id:
        raise SystemExit("Missing GDRIVE_FOLDER_ID")

    # -------------------------------
    # Load week metadata (Week 1 prototype)
    # -------------------------------
    index = load_index()
    week = index[0]

    week_num = int(week["week"])
    week_title = week["title"]
    week_dates = parse_week_dates(week["start_date"], week["end_date"])
    scripture_blocks = week.get("scripture_blocks", "")
    url = week["url"]

    print(f"Generating Week {week_num}: {week_title}")
    print(f"Fetching: {url}")

    # -------------------------------
    # Fetch curriculum text
    # -------------------------------
    cfm_text = fetch_cfm_week_text(url)

    # -------------------------------
    # Generate scripts
    # -------------------------------
    master_prompt = load_master_prompt()
    prompt = build_prompt(
        master=master_prompt,
        week_title=f"Week {week_num}: {week_title}",
        week_dates=week_dates,
        scripture_blocks=scripture_blocks,
        cfm_text=cfm_text,
    )

    print("Generating scripts (4 episodes)...")
    scripts_text = generate_scripts(prompt=prompt, model="gpt-4o-mini")

    # -------------------------------
    # Connect to Google Drive (OAuth)
    # -------------------------------
    print("Connecting to Google Drive...")
    service = get_drive_service_oauth()

    # -------------------------------
    # Create folders
    # -------------------------------
    year_folder = find_or_create_folder(service, "2026 Old Testament", drive_root_id)
    week_folder = find_or_create_folder(
        service, f"Week {week_num:02d} - {week_title}", year_folder
    )
    scripts_folder = find_or_create_folder(service, "scripts", week_folder)
    audio_folder = find_or_create_folder(service, "audio", week_folder)

    # -------------------------------
    # Upload combined script
    # -------------------------------
    upload_text(service, scripts_folder, "all_episodes.txt", scripts_text)

    # -------------------------------
    # Split episodes
    # -------------------------------
    episodes = split_episodes(scripts_text)
    print(f"Split into {len(episodes)} episode(s).")

    if len(episodes) != 4:
        raise SystemExit(
            "Script did not split into 4 episodes. "
            "Check all_episodes.txt for header formatting."
        )

    # -------------------------------
    # Enforce ~10 minute length
    # -------------------------------
    MIN_WORDS = 1300
    MAX_WORDS = 1600

    voice = "alloy"
    tts_model = "tts-1"

    print("Creating MP3s (~10 min each)...")

    for i, ep_text in enumerate(episodes, start=1):
        wc = word_count(ep_text)
        print(f"Episode {i} initial words: {wc}")

        if wc < MIN_WORDS:
            ep_text = expand_to_word_range(ep_text, MIN_WORDS, MAX_WORDS)
            wc = word_count(ep_text)
            print(f"Episode {i} expanded words: {wc}")

            if wc < MIN_WORDS:
                ep_text = expand_to_word_range(ep_text, MIN_WORDS, MAX_WORDS)
                wc = word_count(ep_text)
                print(f"Episode {i} expanded again: {wc}")

        if wc > MAX_WORDS:
            ep_text = shorten_to_word_range(ep_text, MIN_WORDS, MAX_WORDS)
            wc = word_count(ep_text)
            print(f"Episode {i} shortened words: {wc}")

        # Upload script
        upload_text(
            service,
            scripts_folder,
            f"W{week_num:02d}_E{i:02d}.txt",
            ep_text,
        )

        # Generate + upload MP3
        mp3 = tts_to_mp3(ep_text, voice=voice, model=tts_model)
        upload_bytes(
            service,
            audio_folder,
            f"W{week_num:02d}_E{i:02d}.mp3",
            mp3,
            mime_type="audio/mpeg",
        )

        print(f"Uploaded Episode {i}")

    print("SUCCESS — Week 1 complete.")

# ---------------------------------------------------------------------
if __name__ == "__main__":
    main()
