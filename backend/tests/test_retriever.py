import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import RETRIEVAL_SCORE_THRESHOLD
from app.rag.retriever import retrieve


def test_retrieval_returns_relevant_faq_for_known_query():
    result = retrieve("How do I track my order?")
    assert result.max_score >= RETRIEVAL_SCORE_THRESHOLD
    assert any(faq["category"] == "order_tracking" for faq in result.faqs)


def test_retrieval_falls_back_for_out_of_scope_query():
    result = retrieve("what is the meaning of life")
    assert result.max_score < RETRIEVAL_SCORE_THRESHOLD
