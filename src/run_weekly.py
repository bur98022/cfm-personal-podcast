import json
import os
import sys
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, date

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
from src.tts import tts_to_mp3
from src.drive_upload import (
    get_drive_service_oauth,
    find_or_create_folder,
    upload_text,
    upload_bytes,
)


# -----------------------------
# Index + episode helpers
# -----------------------------
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


def strip_show_notes_for_audio(ep_text: str) -> str:
    # Keep everything before SHOW NOTES in the audio.
    return ep_text.split("SHOW NOTES:", 1)[0].strip()


# -----------------------------
# Week selection logic
# -----------------------------
def next_monday_local(tz_name: str = "America/Chicago") -> date:
    """
    Return the date of the next Monday relative to 'now' in tz_name.
    If today is Monday, returns next week's Monday (upcoming week).
    """
    # Python stdlib zoneinfo is available in 3.11+
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(tz_name)).date()
    # Monday = 0 ... Sunday = 6
    days_ahead = (0 - now.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return now + timedelta(days=days_ahead)


def find_week_by_start_date(index: list[dict], start_date_iso: str) -> Optional[dict]:
    for wk in index:
        if wk.get("start_date") == start_date_iso:
            return wk
    return None


# -----------------------------
# Drive helper: check if week already generated
# -----------------------------
def drive_file_exists(service, parent_id: str, filename: str) -> bool:
    safe_name = filename.replace("'", "")
    q = (
        f"'{parent_id}' in parents and trashed=false "
        f"and name='{safe_name}'"
    )
    res = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    return len(files) > 0


def main() -> None:
    print("RUN_WEEKLY: script started")

    # Env checks
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY")

    drive_root_id = os.getenv("GDRIVE_FOLDER_ID")
    if not drive_root_id:
        raise SystemExit("Missing GDRIVE_FOLDER_ID")

    # Load index (batch of ~8 weeks)
    index = load_index()
    if not index:
        raise SystemExit("Index is empty: cfm_index/cfm_2026_index.json")

    # Pick the upcoming week (next Monday start)
    start_dt = next_monday_local("America/Chicago")
    start_iso = start_dt.isoformat()
    week = find_week_by_start_date(index, start_iso)

    if not week:
        raise SystemExit(
            f"No week found in cfm_2026_index.json with start_date={start_iso}.\n"
            "Add the next 8 weeks to the index file and rerun."
        )

    week_num = int(week["week"])
    week_title = week["title"]
    week_dates = f'{week["start_date"]} to {week["end_date"]}'
    scripture_blocks = week.get("scripture_blocks", "")
    url = week["url"]

    print(f"Selected week: {week_num} | {week_dates} | {week_title}")
    print(f"Fetching: {url}")

    # Drive OAuth
    print("Connecting to Google Drive (OAuth)...")
    service = get_drive_service_oauth()

    # Folder naming: based on dates
    year_folder_id = find_or_create_folder(service, "2026 Old Testament", drive_root_id)
    week_folder_name = f'{week["start_date"]} to {week["end_date"]}'
    week_folder_id = find_or_create_folder(service, week_folder_name, year_folder_id)
    scripts_folder_id = find_or_create_folder(service, "scripts", week_folder_id)
    audio_folder_id = find_or_create_folder(service, "audio", week_folder_id)

    # Skip if already generated (look for first MP3)
    already = drive_file_exists(service, audio_folder_id, f"W{week_num:02d}_E01.mp3")
    if already:
        print("This week already appears generated (found W##_E01.mp3). Exiting.")
        return

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

        # Upload script (full text + show notes)
        sid = upload_text(service, scripts_folder_id, f"W{week_num:02d}_E{i:02d}.txt", ep_text)
        print(f"Uploaded script {i} (id={sid})")

        # Audio text excludes show notes
        audio_text = strip_show_notes_for_audio(ep_text)
        mp3 = tts_to_mp3(audio_text, voice=voice, model=tts_model)
        from pathlib import Path

        dist = Path("dist")
        dist.mkdir(parents=True, exist_ok=True)

        mp3_filename = f"W{week_num:02d}_E{i:02d}.mp3"
        mp3_path = dist / mp3_filename
        mp3_path.write_bytes(mp3)

        aid = upload_bytes(
            service,
            audio_folder_id,
            f"W{week_num:02d}_E{i:02d}.mp3",
            mp3,
            mime_type="audio/mpeg",
        )
        print(f"Uploaded audio {i} (id={aid})")

    print("RUN_WEEKLY: done")


if __name__ == "__main__":
    print("RUN_WEEKLY: __main__ reached")
    main()
