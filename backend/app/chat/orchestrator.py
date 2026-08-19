import re
from collections.abc import AsyncIterator

from app.chat import sentiment as sentiment_module
from app.chat.session import TRANSIENT_INTENT, get_history
from app.config import RETRIEVAL_SCORE_THRESHOLD, SENTIMENT_NEGATIVE_THRESHOLD, STORE_NAME
from app.db import crud
from app.db.database import SessionLocal
from app.db.models import Message
from app.llm import prompts
from app.llm.client import stream_grounded_reply
from app.profile.mock_profile import get_profile
from app.rag.retriever import retrieve

# Explicit "get me a person" request - always honoured, so it must stay deterministic
# rather than being left to the model. Matching the bare word "human" or "agent" was far
# too loose: "is there a human review step?" and "the courier agent left a note" are
# questions to answer, not handoff requests. So the request framing has to be present too.
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

HANDOFF_TEMPLATE = (
    "I'm connecting you to a human support agent who can help further. "
    'Here\'s a summary of your message so they have context: "{summary}"'
)

# Soft offer appended to a normal answer - the user stays with the bot unless they take it up.
HUMAN_OFFER_LINE = (
    "\n\nIf that didn't cover it, I can connect you with a human support agent — "
    'just say "talk to a human".'
)

# Used when the FAQs genuinely don't cover the question. We say so plainly instead of
# silently handing off, and let the user decide whether they want a person.
NO_ANSWER_REPLY = (
    "I don't have that in {store}'s support information, so I'd rather not guess. "
    "I can help with order tracking, refunds, returns and exchanges, payments, shipping, "
    "your account, or technical issues."
)


# Shown when the model itself is unreachable - distinct from "the FAQs don't cover this",
# because here we genuinely don't know whether we could have answered.
SERVICE_BUSY_REPLY = (
    "Sorry — I'm having trouble reaching the support service right now. "
    "Please try asking again in a moment."
)


def _handoff_message(user_message: str) -> str:
    summary = user_message if len(user_message) <= 200 else user_message[:200] + "..."
    return HANDOFF_TEMPLATE.format(summary=summary)


def _no_answer_message() -> str:
    return NO_ANSWER_REPLY.format(store=STORE_NAME) + HUMAN_OFFER_LINE


def _retrieve_in_context(message: str, history: list[dict]):
    """
    Retrieve for the message, retrying with the previous question attached if it
    lands under the confidence threshold.

    A follow-up like "i am not able to view that option" has nothing retrievable in
    it on its own; pairing it with what was just asked gives the search something to
    match. Cheaper than an LLM rewrite and it only runs when the first attempt is weak.
    """
    result = retrieve(message)
    if result.max_score >= RETRIEVAL_SCORE_THRESHOLD:
        return result

    previous = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), None
    )
    if not previous:
        return result

    in_context = retrieve(f"{previous} {message}")
    return in_context if in_context.max_score > result.max_score else result


def _log_user_message(session_id: str, message: str) -> None:
    db = SessionLocal()
    try:
        crud.log_message(db, session_id, role="user", content=message)
    finally:
        db.close()


def _log_assistant_message(
    session_id: str,
    content: str,
    intent: str | None,
    sentiment: float | None,
    escalated: bool,
    sources: list[dict] | None,
) -> Message:
    db = SessionLocal()
    try:
        return crud.log_message(
            db,
            session_id,
            role="assistant",
            content=content,
            intent=intent,
            sentiment=sentiment,
            escalated=escalated,
            sources=sources,
        )
    finally:
        db.close()


async def run_turn(session_id: str, message: str, user_id: str | None = None) -> AsyncIterator[tuple[str, dict]]:
    """
    Async generator yielding (event, payload) tuples:
      ("token", {"text": ...})           - incremental reply text
      ("done", {message_id, escalated, intent, sentiment, sources}) - final turn summary
    """
    history = get_history(session_id)

    _log_user_message(session_id, message)

    sentiment_score = sentiment_module.score(message)
    retrieval = _retrieve_in_context(message, history)
    human_requested = bool(HUMAN_REQUEST_PATTERN.search(message))

    # Topic tag for the log and the personalisation branch - the retrieved chunk already
    # carries the category, so there's no separate classifier to keep in step with the KB.
    detected_intent = (
        retrieval.faqs[0]["category"]
        if retrieval.faqs and retrieval.max_score >= RETRIEVAL_SCORE_THRESHOLD
        else "out_of_scope"
    )

    # Only an outright request for a person forces a handoff. An unhappy message gets a
    # real answer plus the offer - escalating on tone alone was far too eager.
    offer_human = not human_requested and sentiment_score < SENTIMENT_NEGATIVE_THRESHOLD

    if human_requested:
        reply = _handoff_message(message)
        yield ("token", {"text": reply})
        msg = _log_assistant_message(session_id, reply, detected_intent, sentiment_score, True, None)
        yield (
            "done",
            {
                "message_id": msg.id,
                "escalated": True,
                "intent": detected_intent,
                "sentiment": sentiment_score,
                "sources": [],
                "human_offered": False,
            },
        )
        return

    llm_messages = prompts.build_messages(retrieval.faqs, history, message)
    if user_id and detected_intent == "order_tracking":
        profile = get_profile(user_id)
        llm_messages.insert(
            1,
            {
                "role": "system",
                "content": (
                    f"Customer profile: name={profile['name']}, "
                    f"last_order_id={profile['last_order_id']}, city={profile['city']}. "
                    "You may reference their last order id if relevant to the question. "
                    "Do not invent any other order details."
                ),
            },
        )
    accumulated = ""
    cannot_answer = False
    llm_failed = False
    for event in stream_grounded_reply(llm_messages):
        if event["type"] == "escalate":
            cannot_answer = True
            break
        if event["type"] == "error":
            llm_failed = True
            break
        accumulated += event["text"]
        yield ("token", {"text": event["text"]})

    # A stream that produced no text at all counts as a failure too. Groq's free tier can
    # truncate a reply to zero tokens (finish_reason="length") when the per-minute budget is
    # nearly spent, which otherwise logs a blank message and renders an empty chat bubble.
    if not cannot_answer and not accumulated.strip():
        llm_failed = True

    # Upstream model unavailable (rate limit, timeout). Close the turn properly so the
    # client still gets a reply and a "done" frame rather than an empty message bubble.
    if llm_failed:
        reply = (SERVICE_BUSY_REPLY if not accumulated else "") + HUMAN_OFFER_LINE
        yield ("token", {"text": reply})
        accumulated += reply
        # Tagged so get_history() leaves it out of the next turn's context - an apology for a
        # momentary outage is not something the model should keep reading back.
        msg = _log_assistant_message(
            session_id, accumulated, TRANSIENT_INTENT, sentiment_score, False, None
        )
        yield (
            "done",
            {
                "message_id": msg.id,
                "escalated": False,
                "intent": detected_intent,
                "sentiment": sentiment_score,
                "sources": [],
                "human_offered": True,
            },
        )
        return

    # The FAQs don't cover this. Say so and offer a person rather than forcing a handoff.
    if cannot_answer:
        reply = _no_answer_message()
        yield ("token", {"text": reply})
        msg = _log_assistant_message(
            session_id, reply, detected_intent, sentiment_score, False, None
        )
        yield (
            "done",
            {
                "message_id": msg.id,
                "escalated": False,
                "intent": detected_intent,
                "sentiment": sentiment_score,
                "sources": [],
                "human_offered": True,
            },
        )
        return

    if offer_human:
        yield ("token", {"text": HUMAN_OFFER_LINE})
        accumulated += HUMAN_OFFER_LINE

    sources = [{"id": faq["id"], "question": faq["question"]} for faq in retrieval.faqs]
    msg = _log_assistant_message(session_id, accumulated, detected_intent, sentiment_score, False, sources)
    yield (
        "done",
        {
            "message_id": msg.id,
            "escalated": False,
            "intent": detected_intent,
            "sentiment": sentiment_score,
            "sources": sources,
            "human_offered": offer_human,
        },
    )
