import json
import time
import requests
from typing import Optional

from bot.validators import OrderParams, validate_order_params, ValidationError
from bot.logging_config import setup_logging

logger = setup_logging()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """You are a trading order parser. Extract order parameters from natural language and return ONLY a JSON object.

Output schema (strict):
{
  "symbol": "string (e.g. BTCUSDT, ETHUSDT — always uppercase, always ends in USDT)",
  "side": "BUY or SELL",
  "order_type": "MARKET or LIMIT or STOP",
  "quantity": number (positive float),
  "price": number or null (required for LIMIT and STOP, null for MARKET)
}

Rules:
- Return ONLY the JSON object. No explanation, no markdown, no code fences.
- If you cannot confidently extract all required fields, return: {"error": "reason"}
- symbol must always end in USDT (e.g. BTC -> BTCUSDT)
- quantity must be a positive number
- price must be null for MARKET orders
"""


class AgentParseError(Exception):
    """Raised when the agent cannot parse the input into valid order params."""
    pass


def parse_order_intent(
    natural_language: str,
    api_key: str,
) -> OrderParams:
    """
    Sends natural language input to OpenRouter and parses the response
    into a validated OrderParams dataclass.

    The LLM output is treated as untrusted — it goes through validators.py
    before anything else touches it.

    Raises AgentParseError if parsing or validation fails.
    """
    logger.info(
        "Agent parsing order intent",
        extra={"input": natural_language},
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": natural_language},
        ],
        "temperature": 0,  
        "max_tokens": 200,
    }

    resp = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code == 429:
                wait = 10 * attempt
                logger.warning(f"OpenRouter rate limited, retrying in {wait}s", extra={"attempt": attempt})
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.Timeout:
            raise AgentParseError("OpenRouter request timed out")
        except requests.exceptions.RequestException as e:
            raise AgentParseError(f"OpenRouter network error: {e}")
    else:
        raise AgentParseError("OpenRouter rate limit exceeded after 3 attempts")

    raw_content = resp.json()["choices"][0]["message"]["content"].strip()

    logger.debug(
        "Agent raw LLM response",
        extra={"raw": raw_content},
    )

    if raw_content.startswith("```"):
        raw_content = raw_content.strip("`").strip()
        if raw_content.startswith("json"):
            raw_content = raw_content[4:].strip()

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        raise AgentParseError(f"LLM returned non-JSON output: {raw_content}")

    if "error" in parsed:
        raise AgentParseError(f"LLM could not parse intent: {parsed['error']}")

    try:
        order_params = validate_order_params(
            symbol=parsed.get("symbol", ""),
            side=parsed.get("side", ""),
            order_type=parsed.get("order_type", ""),
            quantity=parsed.get("quantity"),
            price=parsed.get("price"),
        )
    except ValidationError as e:
        raise AgentParseError(f"Parsed params failed validation: {e}")

    logger.info(
        "Agent successfully parsed order",
        extra={
            "symbol": order_params.symbol,
            "side": order_params.side,
            "type": order_params.order_type,
            "quantity": order_params.quantity,
            "price": order_params.price,
        },
    )

    return order_params