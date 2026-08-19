import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import REVIEW_QUEUE_PATH
from app.db import crud
from app.db.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        rows = crud.get_disliked_messages(db)
    finally:
        db.close()

    queue = [
        {
            "message_id": message.id,
            "session_id": message.session_id,
            "question": message.content,
            "intent": message.intent,
            "feedback_comment": feedback.comment,
            "created_at": message.created_at.isoformat(),
        }
        for message, feedback in rows
    ]

    REVIEW_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

    print(f"Exported {len(queue)} disliked messages to {REVIEW_QUEUE_PATH}")


if __name__ == "__main__":
    main()
