import json
import os
import sys
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, date
import urllib.request
import re

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


# -----------------------------
# Helpers
# -----------------------------
def load_index(path: str = "cfm_index/cfm_2026_index.json") -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def strip_show_notes_for_audio(ep_text: str) -> str:
    return ep_text.split("SHOW NOTES:", 1)[0].strip()


def most_recent_monday_local(tz_name: str = "America/Chicago") -> date:
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo(tz_name)).date()
    return today - timedelta(days=today.weekday())


def next_monday_local(tz_name: str = "America/Chicago") -> date:
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo(tz_name)).date()
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def choose_week_start_date_iso(tz_name: str = "America/Chicago") -> str:
    """
    Sunday -> upcoming Monday week
    Mon–Sat -> current week Monday
    """
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo(tz_name)).date()
    if today.weekday() == 6:  # Sunday
        return next_monday_local(tz_name).isoformat()
    return most_recent_monday_local(tz_name).isoformat()


def find_week_by_start_date(index: list[dict], start_date_iso: str) -> Optional[dict]:
    for wk in index:
        if wk.get("start_date") == start_date_iso:
            return wk
    return None


def head_ok(url: str, timeout: int = 20) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def github_pages_base() -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not repo or "/" not in repo:
        override = os.getenv("PAGES_BASE_URL", "").strip()
        if override:
            return override.rstrip("/")
        raise SystemExit("Missing GITHUB_REPOSITORY and no PAGES_BASE_URL override provided.")
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}"


def split_episodes(all_text: str) -> List[str]:
    """
    Robust splitter.
    Accepts headings like:
      === EPISODE 1: ... ===
      === EPISODE 1 ... ===
      # EPISODE 1: ...
      EPISODE 1: ...
      Episode 1: ...
    Returns 4 chunks in order 1..4 or [] if not possible.
    """
    # Normalize line endings
    txt = all_text.replace("\r\n", "\n").replace("\r", "\n")

    # Find episode header positions using regex
    pattern = re.compile(
        r"(?im)^(?:={3}\s*)?episode\s*([1-4])\s*[:\-].*$|^={3}\s*episode\s*([1-4]).*$|^#\s*episode\s*([1-4]).*$"
    )

    matches = []
    for m in pattern.finditer(txt):
        # pick whichever group matched
        ep_num = next((g for g in m.groups() if g), None)
        if ep_num:
            matches.append((int(ep_num), m.start()))

    # Deduplicate by episode number, keep first occurrence
    pos_by_ep = {}
    for ep, pos in matches:
        if ep not in pos_by_ep:
            pos_by_ep[ep] = pos

    if set(pos_by_ep.keys()) != {1, 2, 3, 4}:
        # Try the strict original headers as a fallback
        strict_headers = [
            "=== EPISODE 1: BIG PICTURE & CONTEXT ===",
            "=== EPISODE 2: SCRIPTURE WALKTHROUGH ===",
            "=== EPISODE 3: DOCTRINES & PRINCIPLES ===",
            "=== EPISODE 4: MODERN LIFE APPLICATION ===",
        ]
        positions = []
        for h in strict_headers:
            idx = txt.find(h)
            if idx != -1:
                positions.append(idx)
        if len(positions) != 4:
            return []
        positions.append(len(txt))
        chunks = []
        for i in range(4):
            chunks.append(txt[positions[i] : positions[i + 1]].strip())
        return chunks

    # Build ordered positions 1..4
    positions = [pos_by_ep[i] for i in (1, 2, 3, 4)]
    # Ensure sorted by position
    positions_sorted = sorted(positions)
    # If ordering is weird, use sorted positions as episode order
    positions = positions_sorted
    positions.append(len(txt))

    chunks = []
    for i in range(4):
        chunks.append(txt[positions[i] : positions[i + 1]].strip())

    # Guard: ensure we didn't accidentally include empty chunks
    if any(len(c) < 50 for c in chunks):
        return []
    return chunks


def enforce_episode_headers_prompt(base_prompt: str) -> str:
    """
    Adds a hard formatting requirement so the model must output split-friendly headers.
    """
    return (
        base_prompt
        + "\n\nIMPORTANT OUTPUT FORMAT:\n"
          "Return EXACTLY 4 episodes in plain text.\n"
          "Each episode MUST start with one of these exact header lines on its own line:\n"
          "=== EPISODE 1: BIG PICTURE & CONTEXT ===\n"
          "=== EPISODE 2: SCRIPTURE WALKTHROUGH ===\n"
          "=== EPISODE 3: DOCTRINES & PRINCIPLES ===\n"
          "=== EPISODE 4: MODERN LIFE APPLICATION ===\n"
          "Do not add any other episode headers. Do not use markdown code fences.\n"
    )


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    print("RUN_WEEKLY: script started")

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY")

    force = os.getenv("FORCE_REGENERATE", "false").lower() == "true"
    print(f"FORCE_REGENERATE={force}")

    index = load_index()
    if not index:
        raise SystemExit("Index is empty: cfm_index/cfm_2026_index.json")

    target_start = os.getenv("TARGET_START_DATE", "").strip()
    if target_start:
        start_iso = target_start
        print(f"TARGET_START_DATE override enabled: {start_iso}")
    else:
        start_iso = choose_week_start_date_iso("America/Chicago")
        print(f"Auto-selected start_date={start_iso}")

    week = find_week_by_start_date(index, start_iso)
    if not week:
        raise SystemExit(
            f"No week found in cfm_2026_index.json with start_date={start_iso}.\n"
            "Verify TARGET_START_DATE or update the index file."
        )

    week_num = int(week["week"])
    week_title = week["title"]
    week_dates = f'{week["start_date"]} to {week["end_date"]}'
    scripture_blocks = week.get("scripture_blocks", "")
    url = week["url"]

    print(f"Selected week: {week_num} | {week_dates} | {week_title}")
    print(f"Fetching: {url}")

    dist = Path("dist")
    dist.mkdir(parents=True, exist_ok=True)

    tag = f"week-{week['start_date']}"
    week_label = f"{week['start_date']} to {week['end_date']}"

    def esc(v: str) -> str:
        return str(v).replace("\n", " ").replace("\r", " ").strip()

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

    pages_base = github_pages_base()
    already_url = f"{pages_base}/media/{tag}/W{week_num:02d}_E01.mp3"

    if head_ok(already_url) and not force:
        print(f"Already published on Pages (found {already_url}). Exiting.")
        return
    if head_ok(already_url) and force:
        print("Already published on Pages, but FORCE_REGENERATE=true — continuing anyway.")

    cfm_text = fetch_cfm_week_text(url)
    print(f"Fetched CFM text length: {len(cfm_text)} chars")

    master = load_master_prompt()
    base_prompt = build_prompt(
        master=master,
        week_title=f"Week {week_num}: {week_title}",
        week_dates=week_dates,
        scripture_blocks=scripture_blocks,
        cfm_text=cfm_text,
    )

    # Try generation up to 2 times; second time forces exact headers
    scripts_text = ""
    episodes: List[str] = []
    for attempt in (1, 2):
        print(f"Generating scripts (4 episodes)... attempt {attempt}/2")
        prompt = base_prompt if attempt == 1 else enforce_episode_headers_prompt(base_prompt)
        scripts_text = generate_scripts(prompt=prompt, model="gpt-4o-mini")
        print(f"Generated scripts length: {len(scripts_text)} chars")

        (dist / "all_episodes.txt").write_text(scripts_text, encoding="utf-8")
        print("Saved dist/all_episodes.txt")

        episodes = split_episodes(scripts_text)
        print(f"Split into {len(episodes)} episode(s).")

        if len(episodes) == 4:
            break

    if len(episodes) != 4:
        raise SystemExit("Could not split into 4 episodes. Check dist/all_episodes.txt output format.")

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

        script_name = f"W{week_num:02d}_E{i:02d}.txt"
        (dist / script_name).write_text(ep_text, encoding="utf-8")
        print(f"Saved dist/{script_name}")

        audio_text = strip_show_notes_for_audio(ep_text)
        mp3 = tts_to_mp3(audio_text, voice=voice, model=tts_model)

        mp3_filename = f"W{week_num:02d}_E{i:02d}.mp3"
        (dist / mp3_filename).write_bytes(mp3)
        print(f"Saved dist/{mp3_filename}")

    print("RUN_WEEKLY: done")


if __name__ == "__main__":
    print("RUN_WEEKLY: __main__ reached")
    main()
