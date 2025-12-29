from __future__ import annotations

from openai import OpenAI

MAX_TTS_CHARS = 3900  # stay under 4096 with a little margin

def _chunk_text(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
    """
    Split text into <= max_chars chunks, preferring paragraph boundaries.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for p in paragraphs:
        # If a single paragraph is too long, hard-wrap it.
        if len(p) > max_chars:
            # flush current first
            flush()
            start = 0
            while start < len(p):
                part = p[start:start + max_chars]
                chunks.append(part.strip())
                start += max_chars
            continue

        # Try to add paragraph to current chunk
        if not current:
            current = p
        elif len(current) + 2 + len(p) <= max_chars:
            current = current + "\n\n" + p
        else:
            flush()
            current = p

    flush()
    return chunks

def tts_to_mp3(text: str, voice: str = "alloy", model: str = "tts-1") -> bytes:
    """
    Convert potentially-long text to MP3 bytes by chunking and concatenating MP3 data.
    NOTE: MP3 concatenation is generally playable in most players/podcast apps.
    """
    client = OpenAI()

    chunks = _chunk_text(text)
    mp3_parts: list[bytes] = []

    for idx, chunk in enumerate(chunks, start=1):
        audio = client.audio.speech.create(
            model=model,
            voice=voice,
            input=chunk,
            response_format="mp3",
        )
        mp3_parts.append(audio.read())

    return b"".join(mp3_parts)
