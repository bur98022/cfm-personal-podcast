import json
import os
import sys
from pathlib import Path
from typing import List

# Ensure repo root is importable (critical for GitHub Actions)
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.cfm_fetch import fetch_cfm_week_text
from src.script_writer import (
    load_master_prompt,
    build_prompt,
    generate_scripts,
    expand_to_word_range,
    shorten_to_word_range,
    word_count,
)
audio_text = ep_text.split("SHOW NOTES:", 1)[0].strip()
mp3 = tts_to_mp3(audio_text, voice=voice, model=tts_model)

from src.tts import tts_to_mp3
from src.drive_upload import (
    get_drive_service_oauth,
    find_or_create_folder,
    upload_text,
    upload_bytes,
)


def load_index(path: str = "cfm_index/cfm_2026_index.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
        chunks.append(all_text[positions[i] : positions[i + 1]].strip())
    return chunks


def main() -> None:
    print("RUN_WEEKLY: script started")

    # Env checks
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY")

    drive_root_id = os.getenv("GDRIVE_FOLDER_ID")
    if not drive_root_id:
        raise SystemExit("Missing GDRIVE_FOLDER_ID")

    # Load index (Week 1 prototype for now)
    index = load_index()
    if not index:
        raise SystemExit("Index is empty: cfm_index/cfm_2026_index.json")

    week = index[0]
    week_num = int(week["week"])
    week_title = week["title"]
    week_dates = f'{week["start_date"]} to {week["end_date"]}'
    scripture_blocks = week.get("scripture_blocks", "")
    url = week["url"]

    print(f"Generating Week {week_num}: {week_title}")
    print(f"Fetching: {url}")

    # Fetch CFM content
    cfm_text = fetch_cfm_week_text(url)
    print(f"Fetched CFM text length: {len(cfm_text)} chars")

    # Generate scripts
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
    print(f"Generated scripts length: {len(scripts_text)} chars")

    # Drive OAuth
    print("Connecting to Google Drive (OAuth)...")
    service = get_drive_service_oauth()

    # Folders
    year_folder_id = find_or_create_folder(service, "2026 Old Testament", drive_root_id)
    week_folder_id = find_or_create_folder(service, f"Week {week_num:02d} - {week_title}", year_folder_id)
    scripts_folder_id = find_or_create_folder(service, "scripts", week_folder_id)
    audio_folder_id = find_or_create_folder(service, "audio", week_folder_id)

    # Upload combined script
    fid = upload_text(service, scripts_folder_id, "all_episodes.txt", scripts_text)
    print(f"Uploaded all_episodes.txt (id={fid})")

    # Split episodes
    episodes = split_episodes(scripts_text)
    print(f"Split into {len(episodes)} episode(s).")
    if len(episodes) != 4:
        raise SystemExit("Could not split into 4 episodes. Check all_episodes.txt headers.")

    # Enforce ~10 minutes
    MIN_WORDS = 1300
    MAX_WORDS = 1600

    voice = "alloy"
    tts_model = "tts-1"

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

        sid = upload_text(service, scripts_folder_id, f"W{week_num:02d}_E{i:02d}.txt", ep_text)
        print(f"Uploaded script {i} (id={sid})")

        audio_text = ep_text.split("SHOW NOTES:", 1)[0].strip()
        mp3 = tts_to_mp3(audio_text, voice=voice, model=tts_model)
        aid = upload_bytes(service, audio_folder_id, f"W{week_num:02d}_E{i:02d}.mp3", mp3, mime_type="audio/mpeg")
        print(f"Uploaded audio {i} (id={aid})")

    print("RUN_WEEKLY: done")


if __name__ == "__main__":
    print("RUN_WEEKLY: __main__ reached")
    main()
