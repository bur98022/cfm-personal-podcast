import re
import requests
from bs4 import BeautifulSoup

def fetch_cfm_week_text(url: str, timeout: int = 30) -> str:
    """
    Fetch and extract readable text from a Come, Follow Me week page.
    This is a best-effort HTML extraction for personal use.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CFMPersonalPodcast/1.0)"
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # Try common containers first
    candidates = []
    for selector in [
        "article",
        "main",
        "div.manual-page",
        "div.content",
        "div.page-content",
    ]:
        node = soup.select_one(selector)
        if node:
            candidates.append(node)

    root = candidates[0] if candidates else soup

    # Remove obvious non-content
    for tag in root.select("nav, header, footer, aside, script, style"):
        tag.decompose()

    text = root.get_text("\n", strip=True)

    # Clean up excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # Keep it from being absurdly large (rare, but safe)
    if len(text) > 120_000:
        text = text[:120_000] + "\n\n[TRUNCATED]"
    return text
