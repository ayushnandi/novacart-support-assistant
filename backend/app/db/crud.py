import json

from sqlalchemy.orm import Session as OrmSession

from app.db.models import Feedback, Message
from app.db.models import Session as SessionModel


def create_session(db: OrmSession, user_id: str | None = None) -> SessionModel:
    session = SessionModel(user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def log_message(
    db: OrmSession,
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    sentiment: float | None = None,
    escalated: bool = False,
    sources: list[dict] | None = None,
) -> Message:
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        sentiment=sentiment,
        escalated=escalated,
        sources_json=json.dumps(sources) if sources else None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_messages(db: OrmSession, session_id: str) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at)
        .all()
    )


def save_feedback(
    db: OrmSession, message_id: str, rating: str, comment: str | None = None
) -> Feedback:
    feedback = Feedback(message_id=message_id, rating=rating, comment=comment)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def get_disliked_messages(db: OrmSession) -> list[tuple[Message, Feedback]]:
    return (
        db.query(Message, Feedback)
        .join(Feedback, Feedback.message_id == Message.id)
        .filter(Feedback.rating == "down")
        .all()
    )
