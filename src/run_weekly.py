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
    return ep_text.split("SHOW NOTES:", 1)[0].strip()


def next_monday_local(tz_name: str = "America/Chicago") -> date:
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(tz_name)).date()
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def find_week_by_start_date(index: list[dict], start_date_iso: str) -> Optional[dict]:
    for wk in index:
        if wk.get("start_date") == start_date_iso:
            return wk
    return None


def drive_file_exists(service, parent_id: str, filename: str) -> bool:
    safe_name = filename.replace("'", "")
    q = f"'{parent_id}' in parents and trashed=false and name='{safe_name}'"
    res = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    return len(res.get("files", [])) > 0


def main() -> None:
    print("RUN_WEEKLY: script started")

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY")

    drive_root_id = os.getenv("GDRIVE_FOLDER_ID")
    if not drive_root_id:
        raise SystemExit("Missing GDRIVE_FOLDER_ID")

    index = load_index()
    if not index:
        raise SystemExit("Index is empty: cfm_index/cfm_2026_index.json")

    start_dt = next_monday_local("America/Chicago")
    start_iso = start_dt.isoformat()
    week = find_week_by_start_date(index, start_iso)

    if not week:
        raise SystemExit(
            f"No week found in cfm_2026_index.json with start_date={start_iso}.\n"
            "Update the index file and rerun."
        )

    week_num = int(week["week"])
    week_title = week["title"]
    week_dates = f'{week["start_date"]} to {week["end_date"]}'
    scripture_blocks = week.get("scripture_blocks", "")
    url = week["url"]

    print(f"Selected week: {week_num} | {week_dates} | {week_title}")
    print(f"Fetching: {url}")

    # Prepare dist/ and write metadata for workflow
    dist = Path("dist")
    dist.mkdir(parents=True, exist_ok=True)

    tag = f"week-{week['start_date']}"
    week_label = f"{week['start_date']} to {week['end_date']}"

    def esc(v: str) -> str:
        # keep env file single-line per key
        return v.replace("\n", " ").replace("\r", " ").strip()

    (dist / "week_meta.env").write_text(
        "PODCAST_TAG={}\n"
        "PODCAST_WEEK_LABEL={}\n"
        "PODCAST_WEEK_NUM={}\n"
        "PODCAST_WEEK_TITLE={}\n"
        "PODCAST_SCRIPTURE_BLOCKS={}\n".format(
            esc(tag),
            esc(week_label),
            week_num,
            esc(week_title),
            esc(scripture_blocks),
        ),
        encoding="utf-8",
    )
    print(f"Wrote week metadata: {tag} | {week_label}")

    service = None
    try:
        print("Connecting to Google Drive (OAuth)...")
        service = get_drive_service_oauth()
    except Exception as e:
        print(f"WARNING: Google Drive auth failed. Continuing without Drive uploads. Error: {e}")


    year_folder_id = find_or_create_folder(service, "2026 Old Testament", drive_root_id)
    week_folder_name = week_label
    week_folder_id = find_or_create_folder(service, week_folder_name, year_folder_id)
    scripts_folder_id = find_or_create_folder(service, "scripts", week_folder_id)
    audio_folder_id = find_or_create_folder(service, "audio", week_folder_id)

    # Skip logic with FORCE_REGENERATE
    force = os.getenv("FORCE_REGENERATE", "false").lower() == "true"

    already = drive_file_exists(
        service,
        audio_folder_id,
        f"W{week_num:02d}_E01.mp3",
    )

    if already and not force:
        print(
            "This week already appears generated in Drive "
            "(found W##_E01.mp3). Exiting."
        )
        return

    if already and force:
        print(
            "FORCE_REGENERATE=true — proceeding even though this week exists in Drive."
        )

    cfm_text = fetch_cfm_week_text(url)
    print(f"Fetched CFM text length: {len(cfm_text)} chars")

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

    fid = upload_text(service, scripts_folder_id, "all_episodes.txt", scripts_text)
    print(f"Uploaded all_episodes.txt (id={fid})")

    episodes = split_episodes(scripts_text)
    print(f"Split into {len(episodes)} episode(s).")
    if len(episodes) != 4:
        raise SystemExit("Could not split into 4 episodes. Check all_episodes.txt headers.")

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

        audio_text = strip_show_notes_for_audio(ep_text)
        mp3 = tts_to_mp3(audio_text, voice=voice, model=tts_model)

        mp3_filename = f"W{week_num:02d}_E{i:02d}.mp3"
        (dist / mp3_filename).write_bytes(mp3)
        print(f"Saved local MP3: dist/{mp3_filename}")

        aid = upload_bytes(
            service,
            audio_folder_id,
            mp3_filename,
            mp3,
            mime_type="audio/mpeg",
        )
        print(f"Uploaded audio {i} (id={aid})")

    print("RUN_WEEKLY: done")


if __name__ == "__main__":
    print("RUN_WEEKLY: __main__ reached")
    main()
