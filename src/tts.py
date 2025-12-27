from openai import OpenAI

def tts_to_mp3(text: str, voice: str = "alloy", model: str = "tts-1") -> bytes:
    """
    Convert text to MP3 bytes using OpenAI TTS.
    model: "tts-1" (fast/cheaper) or "tts-1-hd" (higher quality).
    voice: e.g. "alloy", "verse", etc. (depends on availability for your account).
    """
    client = OpenAI()
    audio = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        format="mp3",
    )
    return audio.read()
