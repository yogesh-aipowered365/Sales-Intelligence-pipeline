import json
import logging
import re
from typing import List, Dict

from openai import OpenAI

from config import load_config

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Strip markdown fences and extract the JSON array from the response."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0)
    return text.strip()


def search_company_options(query: str) -> List[Dict]:
    """
    Use direct API-key based model access to suggest likely company matches.
    Returns a list of dicts: [{name, url, description}, ...]
    """

    config = load_config()

    endpoint = config.azure_endpoint.rstrip("/")

    logger.info("Agent searching for: %s", query)

    client = OpenAI(
        api_key=config.azure_api_key,
        base_url=f"{endpoint}/openai/v1/"
    )

    prompt = (
        f'Search the web for the company "{query}" and find their official website. '
        f'Return up to 3 matching companies as a JSON array in this exact format:\n'
        f'[{{"name": "Company Full Name", "url": "https://www.company.com", '
        f'"description": "One line description of what they do"}}]\n'
        f'Return ONLY the JSON array — no explanation, no markdown code fences, nothing else.'
    )

    response = client.responses.create(
        model=config.azure_deployment,
        input=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    raw = response.output_text.strip()
    cleaned = _extract_json(raw)

    try:
        options = json.loads(cleaned)
        if not isinstance(options, list):
            raise ValueError("Model response was not a JSON array.")

        return [o for o in options if isinstance(o, dict) and o.get("url") and o.get("name")]
    except json.JSONDecodeError:
        logger.error("Could not parse model response as JSON:\n%s", raw)
        raise ValueError(
            f"Model returned unexpected format. Raw response:\n{raw}")
