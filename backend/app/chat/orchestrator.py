import re
from collections.abc import AsyncIterator

from app.chat import sentiment as sentiment_module
from app.chat.session import TRANSIENT_INTENT, get_history
from app.config import RETRIEVAL_SCORE_THRESHOLD, SENTIMENT_NEGATIVE_THRESHOLD, STORE_NAME
from app.db import crud
from app.db.database import SessionLocal
from app.llm import prompts
from app.llm.client import stream_grounded_reply
from app.profile.mock_profile import get_profile
from app.rag.retriever import retrieve

# Matching the bare word "human" or "agent" escalated questions like "is there a human
# review step?", so the request framing has to be there too.
HUMAN_REQUEST_PATTERN = re.compile(
    r"""
      (?:talk|speak|chat|connect|transfer|escalate|put)\s+(?:me\s+)?(?:through\s+)?
          (?:to|with)\s+(?:a|an|the)?\s*
          (?:human|agent|person|representative|rep|someone|somebody)
    | (?:want|need|get)\s+(?:me\s+)?(?:a|an|the)?\s*
          (?:human|real\s+person|live\s+(?:agent|person)|representative)
    | \bhuman\s+(?:support|agent|being|rep\b|representative)
    | \b(?:real|live|actual)\s+(?:human|person|agent)
    | \bcustomer\s+service\s+(?:rep\b|representative)
    """,
    re.IGNORECASE | re.VERBOSE,
)

HANDOFF_REPLY = (
    "I'm connecting you to a human support agent who can help further. "
    'Here\'s a summary of your message so they have context: "{summary}"'
)

HUMAN_OFFER_LINE = (
    "\n\nIf that didn't cover it, I can connect you with a human support agent — "
    'just say "talk to a human".'
)

NO_ANSWER_REPLY = (
    f"I don't have that in {STORE_NAME}'s support information, so I'd rather not guess. "
    "I can help with order tracking, refunds, returns and exchanges, payments, shipping, "
    "your account, or technical issues."
)

SERVICE_BUSY_REPLY = (
    "Sorry — I'm having trouble reaching the support service right now. "
    "Please try asking again in a moment."
)

PROFILE_HINT = (
    "Customer profile: name={name}, last_order_id={last_order_id}, city={city}. "
    "You may reference their last order id if relevant to the question. "
    "Do not invent any other order details."
)


def _log(session_id: str, role: str, content: str, **fields):
    db = SessionLocal()
    try:
        return crud.log_message(db, session_id, role=role, content=content, **fields)
    finally:
        db.close()


def _retrieve_in_context(message: str, history: list[dict]):
    """Retry retrieval with the previous question attached when the first pass is weak.

    A follow-up like "and what if it is late?" has nothing retrievable on its own.
    """
    result = retrieve(message)
    if result.max_score >= RETRIEVAL_SCORE_THRESHOLD:
        return result

    previous = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    if not previous:
        return result

    in_context = retrieve(f"{previous} {message}")
    return in_context if in_context.max_score > result.max_score else result


def _build_messages(faqs: list[dict], history: list[dict], message: str, user_id: str | None,
                    intent: str) -> list[dict]:
    messages = prompts.build_messages(faqs, history, message)
    if user_id and intent == "order_tracking":
        messages.insert(1, {"role": "system", "content": PROFILE_HINT.format(**get_profile(user_id))})
    return messages


async def run_turn(session_id: str, message: str, user_id: str | None = None) -> AsyncIterator[tuple[str, dict]]:
    """Yields ("token", {"text": ...}) as the reply streams, then one ("done", {...})."""
    history = get_history(session_id)
    _log(session_id, "user", message)

    sentiment = sentiment_module.score(message)
    retrieval = _retrieve_in_context(message, history)
    grounded = bool(retrieval.faqs) and retrieval.max_score >= RETRIEVAL_SCORE_THRESHOLD
    intent = retrieval.faqs[0]["category"] if grounded else "out_of_scope"

    def finish(reply: str, *, escalated=False, offered=False, sources=None, log_as=None):
        msg = _log(session_id, "assistant", reply, intent=log_as or intent, sentiment=sentiment,
                   escalated=escalated, sources=sources)
        return ("done", {
            "message_id": msg.id,
            "escalated": escalated,
            "intent": intent,
            "sentiment": sentiment,
            "sources": sources or [],
            "human_offered": offered,
        })

    # Only an outright request for a person forces a handoff; tone alone was far too eager.
    if HUMAN_REQUEST_PATTERN.search(message):
        reply = HANDOFF_REPLY.format(summary=message[:200])
        yield ("token", {"text": reply})
        yield finish(reply, escalated=True)
        return

    reply = ""
    cannot_answer = False
    failed = False
    for event in stream_grounded_reply(_build_messages(retrieval.faqs, history, message, user_id, intent)):
        if event["type"] == "escalate":
            cannot_answer = True
            break
        if event["type"] == "error":
            failed = True
            break
        reply += event["text"]
        yield ("token", {"text": event["text"]})

    # Groq's free tier can truncate a reply to zero tokens once the budget is spent, which
    # would otherwise log a blank message and render an empty chat bubble.
    if not cannot_answer and not reply.strip():
        failed = True

    if failed:
        tail = (SERVICE_BUSY_REPLY if not reply else "") + HUMAN_OFFER_LINE
        yield ("token", {"text": tail})
        # Tagged so get_history() keeps the apology out of the next turn's context.
        yield finish(reply + tail, offered=True, log_as=TRANSIENT_INTENT)
        return

    # We can't answer it, but one unanswerable question isn't a reason to hand off.
    if cannot_answer:
        reply = NO_ANSWER_REPLY + HUMAN_OFFER_LINE
        yield ("token", {"text": reply})
        yield finish(reply, offered=True)
        return

    offer = sentiment < SENTIMENT_NEGATIVE_THRESHOLD
    if offer:
        yield ("token", {"text": HUMAN_OFFER_LINE})
        reply += HUMAN_OFFER_LINE

    sources = [{"id": faq["id"], "question": faq["question"]} for faq in retrieval.faqs]
    yield finish(reply, offered=offer, sources=sources)
