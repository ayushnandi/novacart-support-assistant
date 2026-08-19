from dataclasses import dataclass

from app.config import RETRIEVAL_SCORE_THRESHOLD, RETRIEVAL_TOP_K
from app.rag import keyword_store, vector_store


@dataclass
class RetrievalResult:
    faqs: list[dict]
    max_score: float


def retrieve(query: str, k: int = RETRIEVAL_TOP_K) -> RetrievalResult:
    """FAISS first; fall back to TF-IDF keyword search when vector confidence is low."""
    vector_hits = vector_store.search(query, k=k)
    top_score = vector_hits[0][1] if vector_hits else 0.0

    if top_score >= RETRIEVAL_SCORE_THRESHOLD:
        return RetrievalResult(faqs=[faq for faq, _ in vector_hits], max_score=top_score)

    keyword_hits = keyword_store.search(query, k=k)
    keyword_top = keyword_hits[0][1] if keyword_hits else 0.0
    return RetrievalResult(
        faqs=[faq for faq, _ in keyword_hits],
        max_score=max(top_score, keyword_top),
    )
