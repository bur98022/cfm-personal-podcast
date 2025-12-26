from openai import OpenAI

def tts_to_mp3(text: str, voice: str = "cedar", model: str = "gpt-4o-mini-tts") -> bytes:
    """
    Convert text to MP3 bytes using OpenAI TTS.
    """
    client = OpenAI()
    audio = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        format="mp3",
    )
    return audio.read()
