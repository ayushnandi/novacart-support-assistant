import logging
from collections.abc import Iterator

from openai import OpenAI, OpenAIError

from app.config import ESCALATE_SENTINEL, GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL

logger = logging.getLogger(__name__)

# Groq's free tier caps tokens-per-minute, and a burst of turns trips it. The SDK honours
# the Retry-After header, so a few extra attempts ride out the window instead of failing.
_client = OpenAI(
    base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY or "not-set", max_retries=2
)

_BUFFER_FLUSH_LEN = 15
_BUFFER_MIN_WHITESPACE_LEN = 8


def stream_completion(messages: list[dict]) -> Iterator[str]:
    """Yields raw text deltas from Groq as they arrive."""
    stream = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        stream=True,
        tool_choice="none",
        extra_body={"reasoning_format": "hidden"},
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def stream_grounded_reply(messages: list[dict]) -> Iterator[dict]:
    """
    Streams the LLM reply while guarding against leaking the literal ESCALATE
    sentinel to the client token-by-token. Buffers the first few characters
    until it's unambiguous whether the whole reply is the bare sentinel, then
    either yields a single {"type": "escalate"} event or flushes the buffer
    and streams the remainder live as {"type": "text", "text": ...} events.
    """
    buffer = ""
    flushed = False

    try:
        for delta in stream_completion(messages):
            if flushed:
                yield {"type": "text", "text": delta}
                continue

            buffer += delta
            reached_threshold = len(buffer) >= _BUFFER_FLUSH_LEN or (
                len(buffer) >= _BUFFER_MIN_WHITESPACE_LEN and buffer[-1].isspace()
            )
            if reached_threshold:
                if buffer.strip() == ESCALATE_SENTINEL:
                    yield {"type": "escalate"}
                    return
                flushed = True
                yield {"type": "text", "text": buffer}
    except OpenAIError as exc:
        # Rate limit, timeout, upstream outage. Let the caller say something useful
        # instead of the exception tearing down the SSE stream mid-reply.
        logger.warning("LLM call failed: %s", exc)
        yield {"type": "error", "partial": buffer if flushed else ""}
        return

    if not flushed:
        if buffer.strip() == ESCALATE_SENTINEL:
            yield {"type": "escalate"}
        elif buffer:
            yield {"type": "text", "text": buffer}
