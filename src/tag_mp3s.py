import os
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TDRC
from mutagen.mp3 import MP3

EP_TITLES = {
    "E01": "Big Picture & Context",
    "E02": "Scripture Walkthrough",
    "E03": "Doctrines & Principles",
    "E04": "Modern Life Application",
}

def main():
    dist = Path("dist")
    mp3s = sorted(dist.glob("W*_E*.mp3"))
    if not mp3s:
        raise SystemExit("No MP3s found in dist/ to tag.")

    week_label = os.environ.get("PODCAST_WEEK_LABEL", "").strip()
    week_num = os.environ.get("PODCAST_WEEK_NUM", "").strip()
    week_title = os.environ.get("PODCAST_WEEK_TITLE", "").strip()

    podcast_title = "CFM Personal Podcast"
    artist = "Brandon Burton"
    album = f"{podcast_title} — {week_label}" if week_label else podcast_title

    for mp3_path in mp3s:
        fname = mp3_path.name  # W02_E01.mp3
        ecode = fname.split("_")[-1].replace(".mp3", "")  # E01
        ep_num = ecode.replace("E", "")  # 01
        ep_name = EP_TITLES.get(ecode, ecode)

        title = f"Week {week_num} ({week_label}) — Episode {ep_num}: {ep_name}"
        if week_title:
            title += f" — {week_title}"

        # Ensure file is a valid MP3
        _ = MP3(mp3_path)

        try:
            tags = ID3(mp3_path)
        except Exception:
            tags = ID3()

        tags.delall("TIT2")
        tags.delall("TPE1")
        tags.delall("TALB")
        tags.delall("TRCK")
        tags.delall("TDRC")

        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))
        tags.add(TALB(encoding=3, text=album))
        tags.add(TRCK(encoding=3, text=str(int(ep_num))))
        tags.add(TDRC(encoding=3, text="2026"))

        tags.save(mp3_path)
        print(f"Tagged: {mp3_path}")

if __name__ == "__main__":
    main()
