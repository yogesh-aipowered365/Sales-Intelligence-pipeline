import json
import logging

from openai import AzureOpenAI

from config import Config
from models import SalesBrief

logger = logging.getLogger(__name__)

MAX_WORDS = 12_000

SYSTEM_PROMPT = (
    "You are a B2B sales intelligence analyst. Your job is to read raw website content "
    "and extract a structured brief that a presales consultant will use to prepare for a "
    "first meeting with this company. Be specific and factual. Only include what is supported "
    "by the content. Do not invent information."
)


def _build_user_prompt(markdown: str) -> str:
    return (
        "Read the following website content and extract a sales intelligence brief.\n\n"
        "Return ONLY a valid JSON object matching this schema — no explanation, "
        "no markdown code fences, no extra text:\n\n"
        f"{json.dumps(SalesBrief.model_json_schema(), indent=2)}\n\n"
        f"Website content:\n\n{markdown}"
    )


def _truncate(markdown: str) -> str:
    words = markdown.split()
    if len(words) > MAX_WORDS:
        logger.warning(
            "Content exceeds %s words (%s words). Truncating.",
            MAX_WORDS,
            len(words),
        )
        return " ".join(words[:MAX_WORDS])
    return markdown


def _parse_response(raw: str) -> SalesBrief | None:
    try:
        parsed = json.loads(raw)
        return SalesBrief(**parsed)
    except Exception:
        return None


def extract_sales_brief(markdown: str, config: Config) -> SalesBrief:
    """
    Extract a structured sales brief using Azure OpenAI / Foundry model inference
    with API key authentication only.
    """

    client = AzureOpenAI(
        api_key=config.azure_api_key,
        azure_endpoint=config.azure_endpoint.rstrip("/"),
        api_version=config.azure_api_version,
    )

    logger.info("Endpoint: %s", config.azure_endpoint)
    logger.info("Deployment: %s", config.azure_deployment)
    logger.info("API Version: %s", config.azure_api_version)

    markdown = _truncate(markdown)
    user_prompt = _build_user_prompt(markdown)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = client.chat.completions.create(
        model=config.azure_deployment,
        messages=messages,
        temperature=0.2,
    )

    raw = (response.choices[0].message.content or "").strip()

    brief = _parse_response(raw)
    if brief:
        return brief

    logger.warning(
        "JSON parsing failed on first attempt. Retrying with explicit reminder."
    )

    messages.append({"role": "assistant", "content": raw})
    messages.append(
        {
            "role": "user",
            "content": (
                "Your response was not valid JSON. Please return ONLY the JSON object — "
                "no explanation, no markdown code fences, nothing else."
            ),
        }
    )

    retry_response = client.chat.completions.create(
        model=config.azure_deployment,
        messages=messages,
        temperature=0.1,
    )

    raw_retry = (retry_response.choices[0].message.content or "").strip()

    brief = _parse_response(raw_retry)
    if brief:
        return brief

    raise ValueError(
        f"Failed to parse JSON response after retry.\nRaw response:\n{raw_retry}"
    )
