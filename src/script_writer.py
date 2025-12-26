import pathlib
from openai import OpenAI

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
    """
    Returns one big text response containing 5 episode scripts + show notes.
    """
    client = OpenAI()
    resp = client.responses.create(
        model=model,
        input=prompt,
    )
    return resp.output_text
