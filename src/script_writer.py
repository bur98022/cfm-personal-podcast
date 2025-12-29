import pathlib
from openai import OpenAI
from openai import RateLimitError, APIStatusError

def load_master_prompt(path: str = "prompts/master_prompt.txt") -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")

def build_prompt(master: str, week_title: str, week_dates: str, scripture_blocks: str, cfm_text: str) -> str:
    return (
        master.replace("{WEEK_TITLE}", week_title)
              .replace("{WEEK_DATES}", week_dates)
              .replace("{SCRIPTURE_BLOCKS}", scripture_blocks)
              .replace("{CFM_TEXT}", cfm_text)
    )

def generate_scripts(prompt: str, model: str = "gpt-4o-mini") -> str:
    client = OpenAI()
    try:
        resp = client.responses.create(model=model, input=prompt)
        return resp.output_text
    except RateLimitError as e:
        raise SystemExit(
            "OpenAI API rate limit / quota issue.\n"
            "Fix: Check OpenAI Platform billing for the API key used in GitHub Secrets.\n"
            f"Details: {e}"
        )
    except APIStatusError as e:
        raise SystemExit(f"OpenAI API error: {e}")

def shorten_to_word_range(text: str, min_words: int, max_words: int, model: str = "gpt-4o-mini") -> str:
    """
    If a script is too long, ask the model to shorten it while keeping structure.
    This is cheap at your 10-min scale and prevents huge TTS runs.
    """
    client = OpenAI()
    prompt = (
        "Shorten the script below to fit the target length while preserving meaning, tone, and structure.\n"
        f"Target: {min_words}-{max_words} words.\n"
        "Rules:\n"
        "- Keep it natural spoken audio.\n"
        "- Preserve key points, scriptures, and 'Pause & Ponder' questions.\n"
        "- Do not add new sources.\n\n"
        "SCRIPT:\n"
        f"{text}"
    )
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text
def expand_to_word_range(text: str, min_words: int, max_words: int, model: str = "gpt-4o-mini") -> str:
    """
    If a script is too short, expand it within the target range by adding
    more explanation, examples, and transitions—without adding new sources.
    """
    client = OpenAI()
    prompt = (
    "Expand the script below to fit the target length while preserving meaning, tone, and structure.\n"
    f"Target: {min_words}-{max_words} words. IMPORTANT: you MUST reach at least {min_words} words.\n"
    "Rules:\n"
    "- Keep it natural spoken audio.\n"
    "- Add more explanation, more transitions, and 2-3 additional modern-life examples.\n"
    "- Add one additional 'Pause & Ponder' question if needed.\n"
    "- Do not add new sources beyond what is already present.\n"
    "- Do not remove existing sections.\n\n"
    "SCRIPT:\n"
    f"{text}"
)

    )
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text

def word_count(s: str) -> int:
    return len([w for w in s.split() if w.strip()])
