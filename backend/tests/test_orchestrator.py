import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.chat.orchestrator import run_turn
from app.db.database import engine
from app.db.models import Base

Base.metadata.create_all(bind=engine)


async def _collect(session_id: str, message: str):
    events = []
    async for event, payload in run_turn(session_id, message):
        events.append((event, payload))
    return events


def _done(events: list) -> dict:
    done_events = [payload for event, payload in events if event == "done"]
    assert len(done_events) == 1
    return done_events[0]


@pytest.mark.asyncio
async def test_out_of_scope_query_offers_a_human_instead_of_handing_off():
    """We can't answer it, but one unanswerable question is not a reason to hand off."""
    session_id = str(uuid.uuid4())
    done = _done(await _collect(session_id, "can you tell me a joke about pizza"))

    assert done["escalated"] is False
    assert done["human_offered"] is True


@pytest.mark.asyncio
async def test_explicit_human_request_escalates():
    session_id = str(uuid.uuid4())
    done = _done(await _collect(session_id, "i want to talk to a human please"))

    assert done["escalated"] is True


@pytest.mark.asyncio
async def test_frustration_offers_a_human_but_does_not_force_one():
    session_id = str(uuid.uuid4())
    done = _done(
        await _collect(session_id, "this is terrible my refund is so late and im upset")
    )

    assert done["escalated"] is False, "tone alone should not hand off"
    assert done["human_offered"] is True, "frustration should surface the human option"


@pytest.mark.asyncio
async def test_greeting_gets_a_reply_and_does_not_escalate():
    """Greetings are handled by the prompt, so a bare 'hi' must still get real text back."""
    session_id = str(uuid.uuid4())
    events = await _collect(session_id, "hi")
    done = _done(events)

    assert done["escalated"] is False
    reply = "".join(p["text"] for e, p in events if e == "token")
    assert len(reply) > 20, f"greeting produced no usable reply: {reply!r}"


@pytest.mark.asyncio
async def test_conversation_meta_questions_survive_out_of_scope_turns():
    """
    "What did I ask you first?" must be answered from history, not refused.

    Regression: the canned out-of-scope reply is logged like any other assistant turn, so
    after two of them in a row the model copied the pattern and refused a question about
    the conversation itself - which it could always have answered.
    """
    session_id = str(uuid.uuid4())
    await _collect(session_id, "hi there")
    await _collect(session_id, "how do i track my order?")
    await _collect(session_id, "what is the capital of france?")
    await _collect(session_id, "tell me a joke about pizza")

    events = await _collect(session_id, "what was the very first thing i asked you about?")
    reply = "".join(p["text"] for e, p in events if e == "token").lower()

    assert "rather not guess" not in reply, f"fell back to the out-of-scope reply: {reply!r}"
    assert _done(events)["human_offered"] is False
