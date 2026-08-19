from app.config import HISTORY_CHAR_BUDGET
from app.db import crud
from app.db.database import SessionLocal

# Turns the assistant produced when the model was unreachable. They are kept in the database
# (they were shown to the user, and carry a message_id for feedback) but replaying them as
# context just teaches the model to keep apologising for an outage that has already passed.
TRANSIENT_INTENT = "service_error"


def get_history(session_id: str) -> list[dict]:
    """
    The conversation so far, oldest first, as OpenAI-style role/content dicts.

    The whole session is kept rather than a fixed number of turns, so the assistant can still
    answer "what did I ask you first?" late in a long chat. The only cap is size: once the
    transcript would crowd out the system prompt, the oldest messages drop off, which is what
    any chat client does. Trimming walks backwards so the most recent turns always survive.
    """
    db = SessionLocal()
    try:
        messages = crud.get_messages(db, session_id)
    finally:
        db.close()

    kept: list[dict] = []
    remaining = HISTORY_CHAR_BUDGET

    for message in reversed(messages):
        if message.intent == TRANSIENT_INTENT or not message.content.strip():
            continue
        remaining -= len(message.content)
        if remaining < 0:
            break
        kept.append({"role": message.role, "content": message.content})

    kept.reverse()
    return kept
