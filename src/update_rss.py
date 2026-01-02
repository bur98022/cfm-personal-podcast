import os
from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import html

RSS_PATH = Path("docs/podcast.xml")

EPISODE_TITLES = {
    "E01": "Big Picture & Context",
    "E02": "Scripture Walkthrough",
    "E03": "Doctrines & Principles",
    "E04": "Modern Life Application",
}

def rfc2822_now() -> str:
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def get_existing_guids(channel) -> set[str]:
    guids = set()
    for item in channel.findall("item"):
        g = item.findtext("guid")
        if g:
            guids.add(g.strip())
    return guids

def main():
    repo = os.environ["GITHUB_REPOSITORY"]  # OWNER/REPO
    tag = os.environ["PODCAST_TAG"]
    week_label = os.environ["PODCAST_WEEK_LABEL"]
    week_num = os.environ.get("PODCAST_WEEK_NUM", "").strip()
    week_title = os.environ.get("PODCAST_WEEK_TITLE", "").strip()
    scripture_blocks = os.environ.get("PODCAST_SCRIPTURE_BLOCKS", "").strip()

    # Use GitHub Pages to host MP3s (best compatibility)
    # MP3s live at: docs/media/<tag>/<file>.mp3  --> Pages serves them at /media/<tag>/<file>.mp3
    pages_base = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}"
    media_base = f"{pages_base}/media/{tag}"

    show_link = f"https://github.com/{repo}"
    pubdate = rfc2822_now()

    tree = ET.parse(RSS_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise SystemExit("Invalid RSS: missing <channel>")

    existing_guids = get_existing_guids(channel)

    media_dir = Path("docs") / "media" / tag
    mp3s = sorted(media_dir.glob("W*_E*.mp3"))
    if not mp3s:
        raise SystemExit(f"No MP3s found in {media_dir}")

    # Add newest items at top
    for mp3 in sorted(mp3s, reverse=True):
        fname = mp3.name
        size = mp3.stat().st_size
        url = f"{media_base}/{fname}"

        ecode = fname.split("_")[-1].replace(".mp3", "").strip()  # E01
        nice_ep = EPISODE_TITLES.get(ecode, ecode)
        guid_value = f"{tag}:{fname}"

        if guid_value in existing_guids:
            print(f"RSS: skipping existing item (guid={guid_value})")
            continue

        item = ET.Element("item")

        title_el = ET.SubElement(item, "title")
        if week_num:
            title_el.text = html.escape(f"Week {week_num} ({week_label}) — Episode {ecode[-2:]}: {nice_ep}")
        else:
            title_el.text = html.escape(f"Week {week_label} — Episode {ecode[-2:]}: {nice_ep}")

        desc_el = ET.SubElement(item, "description")
        parts = []
        if week_title:
            parts.append(week_title)
        if scripture_blocks:
            parts.append(f"Study: {scripture_blocks}")
        parts.append(f"Week: {week_label}")
        desc_el.text = html.escape(" | ".join([p for p in parts if p]))

        link_el = ET.SubElement(item, "link")
        link_el.text = show_link

        guid_el = ET.SubElement(item, "guid")
        guid_el.text = guid_value
        guid_el.set("isPermaLink", "false")

        pub_el = ET.SubElement(item, "pubDate")
        pub_el.text = pubdate

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", url)
        enclosure.set("length", str(size))
        enclosure.set("type", "audio/mpeg")

        channel.insert(0, item)
        existing_guids.add(guid_value)
        print(f"RSS: added {fname} -> {url}")

    tree.write(RSS_PATH, encoding="utf-8", xml_declaration=True)
    print("RSS: podcast.xml updated successfully")

if __name__ == "__main__":
    main()
