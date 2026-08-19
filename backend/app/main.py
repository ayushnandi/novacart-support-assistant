import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as OrmSession

from app.chat.orchestrator import run_turn
from app.db import crud
from app.db.database import engine, get_db
from app.db.models import Base
from app.profile.mock_profile import get_profile
from app.pydantic_models import (
    ChatRequest,
    FeedbackRequest,
    FeedbackResponse,
    MessageOut,
    ProfileResponse,
    SessionResponse,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="NovaCart Support Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://localhost:\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/session", response_model=SessionResponse)
def create_session(user_id: str | None = None, db: OrmSession = Depends(get_db)):
    session = crud.create_session(db, user_id=user_id)
    return SessionResponse(session_id=session.id)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_chat(session_id: str, message: str, user_id: str | None):
    async for event, payload in run_turn(session_id, message, user_id):
        yield _sse_event(event, payload)


@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _stream_chat(request.session_id, request.message, request.user_id),
        media_type="text/event-stream",
    )


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest, db: OrmSession = Depends(get_db)):
    if request.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    fb = crud.save_feedback(db, request.message_id, request.rating, request.comment)
    return FeedbackResponse(id=fb.id, message_id=fb.message_id, rating=fb.rating)


@app.get("/logs", response_model=list[MessageOut])
def logs(session_id: str, db: OrmSession = Depends(get_db)):
    messages = crud.get_messages(db, session_id)
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            sentiment=m.sentiment,
            escalated=m.escalated,
            sources=json.loads(m.sources_json) if m.sources_json else None,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@app.get("/profile/{user_id}", response_model=ProfileResponse)
def profile(user_id: str):
    return ProfileResponse(**get_profile(user_id))
