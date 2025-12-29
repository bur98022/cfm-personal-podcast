from openai import OpenAI

def tts_to_mp3(text: str, voice: str = "alloy", model: str = "tts-1") -> bytes:
    """
    Convert text to MP3 bytes using OpenAI TTS.
    Some SDK versions use response_format rather than format.
    """
    client = OpenAI()
    audio = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format="mp3",
    )
    return audio.read()
