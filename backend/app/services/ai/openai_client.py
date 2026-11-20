import logging
import os

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
CHATBOT_TIMEOUT = int(os.getenv("CHATBOT_TIMEOUT", "30"))

client = (
    OpenAI(api_key=OPENAI_API_KEY, timeout=CHATBOT_TIMEOUT) if OPENAI_API_KEY else None
)


def create_chat_completion(request_kwargs: dict, _retried_params: set | None = None):
    """Call the Chat Completions API, dropping any parameter OpenAI reports as
    unsupported for the configured model and retrying once. Some model families
    (e.g. reasoning models) reject params like `temperature` or repurpose
    `max_tokens` as `max_completion_tokens`; this keeps callers working across
    model swaps in `.env` without needing a code change each time."""
    retried_params = _retried_params or set()
    try:
        return client.chat.completions.create(**request_kwargs)
    except BadRequestError as exc:
        body = getattr(exc, "body", None) or {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        param = error.get("param")
        if (
            error.get("code") == "unsupported_parameter"
            and param in request_kwargs
            and param not in retried_params
        ):
            logger.warning(
                "OpenAI model %s does not support '%s'; retrying without it.",
                OPENAI_MODEL,
                param,
            )
            next_kwargs = {k: v for k, v in request_kwargs.items() if k != param}
            return create_chat_completion(next_kwargs, retried_params | {param})
        raise
