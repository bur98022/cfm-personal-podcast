import os
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TDRC
from mutagen.mp3 import MP3

def main():
    dist = Path("dist")
    mp3s = sorted(dist.glob("W*_E*.mp3"))
    if not mp3s:
        raise SystemExit("No MP3s found in dist/ to tag.")

    week_label = os.environ.get("PODCAST_WEEK_LABEL", "").strip()
    week_num = os.environ.get("PODCAST_WEEK_NUM", "").strip()
    week_title = os.environ.get("PODCAST_WEEK_TITLE", "").strip()
    scripture_blocks = os.environ.get("PODCAST_SCRIPTURE_BLOCKS", "").strip()

    podcast_title = "CFM Personal Podcast"
    artist = "Brandon Burton"

    for mp3_path in mp3s:
        fname = mp3_path.name  # e.g., W02_E01.mp3
        # Track number = episode number
        ep = fname.split("_")[-1].replace(".mp3", "")  # E01
        track_num = ep.replace("E", "")  # 01

        # Build a nice title
        base_title = f"Week {week_num} ({week_label}) - Episode {track_num}"
        if week_title:
            base_title += f": {week_title}"

        album = f"{podcast_title} — {week_label}" if week_label else podcast_title

        # Write ID3 tags
        audio = MP3(mp3_path)
        try:
            tags = ID3(mp3_path)
        except Exception:
            tags = ID3()

        tags.delall("TIT2")
        tags.delall("TPE1")
        tags.delall("TALB")
        tags.delall("TRCK")
        tags.delall("TDRC")

        tags.add(TIT2(encoding=3, text=base_title))
        tags.add(TPE1(encoding=3, text=artist))
        tags.add(TALB(encoding=3, text=album))
        tags.add(TRCK(encoding=3, text=str(int(track_num))))
        tags.add(TDRC(encoding=3, text="2026"))

        tags.save(mp3_path)

        # Touch MP3 again to ensure file is readable
        _ = MP3(mp3_path)
        print(f"Tagged: {mp3_path}")

if __name__ == "__main__":
    main()
