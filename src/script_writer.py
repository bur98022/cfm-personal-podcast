import pathlib
from openai import OpenAI
from openai import RateLimitError, APIStatusError


def load_master_prompt(path: str = "prompts/master_prompt.txt") -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def build_prompt(
    master: str,
    week_title: str,
    week_dates: str,
    scripture_blocks: str,
    cfm_text: str,
) -> str:
    return (
        master.replace("{WEEK_TITLE}", week_title)
        .replace("{WEEK_DATES}", week_dates)
        .replace("{SCRIPTURE_BLOCKS}", scripture_blocks)
        .replace("{CFM_TEXT}", cfm_text)
    )


def generate_scripts(prompt: str, model: str = "gpt-4o-mini") -> str:
    client = OpenAI()
    try:
        resp = client.responses.create(
            model=model,
            input=prompt,
        )
        return resp.output_text
    except RateLimitError as e:
        raise SystemExit(
            "OpenAI rate limit or quota issue.\n"
            "Check billing for the API key in GitHub Secrets.\n"
            f"Details: {e}"
        )
    except APIStatusError as e:
        raise SystemExit(f"OpenAI API error: {e}")


def shorten_to_word_range(
    text: str,
    min_words: int,
    max_words: int,
    model: str = "gpt-4o-mini",
) -> str:
    client = OpenAI()
    prompt = (
        "Shorten the script below to fit the target length while preserving meaning, tone, and structure.\n"
        f"Target: {min_words}-{max_words} words.\n"
        "Rules:\n"
        "- Natural spoken audio\n"
        "- Keep scriptures and Pause & Ponder questions\n"
        "- Do not add new sources\n\n"
        "SCRIPT:\n"
        f"{text}"
    )
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text


def expand_to_word_range(
    text: str,
    min_words: int,
    max_words: int,
    model: str = "gpt-4o-mini",
) -> str:
    client = OpenAI()
    prompt = (
        "Expand the script below to fit the target length while preserving meaning, tone, and structure.\n"
        f"Target: {min_words}-{max_words} words. You MUST reach at least {min_words} words.\n"
        "Rules:\n"
        "- Natural spoken audio\n"
        "- Add more explanation and modern-life examples\n"
        "- Keep existing scriptures\n"
        "- Do not add new sources\n\n"
        "SCRIPT:\n"
        f"{text}"
    )
    resp = client.responses.create(model=model, input=prompt)
    return resp.output_text


def word_count(text: str) -> int:
    return len([w for w in text.split() if w.strip()])
