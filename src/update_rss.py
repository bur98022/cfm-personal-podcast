import os
from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

RSS_PATH = Path("docs/podcast.xml")

def rfc2822_now():
    return datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

def main():
    repo = os.environ["GITHUB_REPOSITORY"]          # OWNER/REPO
    tag = os.environ["PODCAST_TAG"]                # week-YYYY-MM-DD
    week_label = os.environ["PODCAST_WEEK_LABEL"]  # YYYY-MM-DD to YYYY-MM-DD

    base = f"https://github.com/{repo}/releases/download/{tag}"
    show_link = f"https://github.com/{repo}"
    pubdate = rfc2822_now()

    tree = ET.parse(RSS_PATH)
    root = tree.getroot()
    channel = root.find("channel")

    dist = Path("dist")
    mp3s = sorted(dist.glob("W*_E*.mp3"))
    if not mp3s:
        raise SystemExit("No MP3s found in dist/")

    for mp3 in mp3s:
        fname = mp3.name
        size = mp3.stat().st_size

        item = ET.Element("item")

        title = ET.SubElement(item, "title")
        title.text = f"Week {week_label} – {fname.replace('.mp3','')}"

        desc = ET.SubElement(item, "description")
        desc.text = f"Come, Follow Me companion episode ({week_label})."

        link = ET.SubElement(item, "link")
        link.text = show_link

        guid = ET.SubElement(item, "guid")
        guid.text = f"{tag}:{fname}"
        guid.set("isPermaLink", "false")

        pub = ET.SubElement(item, "pubDate")
        pub.text = pubdate

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", f"{base}/{fname}")
        enclosure.set("length", str(size))
        enclosure.set("type", "audio/mpeg")

        channel.insert(0, item)

    tree.write(RSS_PATH, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
