import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chat.session import TRANSIENT_INTENT, get_history
from app.config import HISTORY_CHAR_BUDGET
from app.db import crud
from app.db.database import SessionLocal, engine
from app.db.models import Base

Base.metadata.create_all(bind=engine)


def _session_with(turns: list[tuple[str, str]], intent: str | None = None) -> str:
    db = SessionLocal()
    try:
        session_id = crud.create_session(db).id
        for role, content in turns:
            crud.log_message(
                db, session_id, role=role, content=content,
                intent=intent if role == "assistant" else None,
            )
    finally:
        db.close()
    return session_id


def test_short_conversation_is_kept_whole():
    """No fixed turn window: the opening message is still there many turns later."""
    turns = []
    for i in range(20):
        turns.append(("user", f"question number {i}"))
        turns.append(("assistant", f"answer number {i}"))

    history = get_history(_session_with(turns))

    assert len(history) == 40, "a normal-length chat should not be trimmed at all"
    assert history[0]["content"] == "question number 0"
    assert history[-1]["content"] == "answer number 19"


def test_oversized_conversation_drops_oldest_and_keeps_recent():
    filler = "x" * 1000
    turns = [("user", filler), ("assistant", filler)] * 10  # 20k chars, over budget

    history = get_history(_session_with(turns))
    total = sum(len(m["content"]) for m in history)

    assert total <= HISTORY_CHAR_BUDGET, "history must stay inside the prompt budget"
    assert len(history) < 20, "something should have been dropped"
    assert history[-1]["content"] == filler, "the most recent turn must always survive"


def test_outage_replies_are_not_replayed_as_context():
    """A 'service unavailable' apology stays in the log but out of the next prompt."""
    session_id = _session_with(
        [("user", "how do i track my order"), ("assistant", "sorry, service is down")],
        intent=TRANSIENT_INTENT,
    )

    history = get_history(session_id)

    assert [m["role"] for m in history] == ["user"]
    assert all("service is down" not in m["content"] for m in history)
