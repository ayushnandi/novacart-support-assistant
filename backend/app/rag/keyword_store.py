import json
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import KB_CHUNKS_PATH


@lru_cache(maxsize=1)
def _index():
    # Same corpus the FAISS index was built from, so the fallback can't drift out of sync.
    with open(KB_CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(
        [f"{c['question']}\n{c['answer']}" for c in chunks]
    )
    return vectorizer, matrix, chunks


def search(query: str, k: int = 3) -> list[tuple[dict, float]]:
    vectorizer, matrix, chunks = _index()
    query_vec = vectorizer.transform([query])
    scores = cosine_similarity(query_vec, matrix)[0]
    top_indices = scores.argsort()[::-1][:k]
    return [(chunks[i], float(scores[i])) for i in top_indices]
