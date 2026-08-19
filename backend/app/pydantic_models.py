from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: str | None = None


class FeedbackRequest(BaseModel):
    message_id: str
    rating: str  # "up" | "down"
    comment: str | None = None


class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    rating: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    intent: str | None
    sentiment: float | None
    escalated: bool
    sources: list[dict] | None
    created_at: str


class ProfileResponse(BaseModel):
    name: str
    membership_tier: str
    last_order_id: str | None
    city: str | None
