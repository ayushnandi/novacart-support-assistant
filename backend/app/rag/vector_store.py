from functools import lru_cache

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import EMBEDDING_MODEL_NAME, INDEX_DIR

INDEX_NAME = "kb"


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    # Normalised vectors + inner-product distance = cosine similarity, so scores stay
    # in the 0..1 range RETRIEVAL_SCORE_THRESHOLD is tuned against.
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        encode_kwargs={"normalize_embeddings": True},
    )


def build(documents: list[Document]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store = FAISS.from_documents(
        documents,
        get_embeddings(),
        distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
    )
    store.save_local(str(INDEX_DIR), index_name=INDEX_NAME)


@lru_cache(maxsize=1)
def _store() -> FAISS:
    if not (INDEX_DIR / f"{INDEX_NAME}.faiss").exists():
        raise FileNotFoundError(
            "Knowledge-base index not found. Run scripts/build_index.py first."
        )
    return FAISS.load_local(
        str(INDEX_DIR),
        get_embeddings(),
        index_name=INDEX_NAME,
        distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
        # Safe: this index is generated locally by our own build script.
        allow_dangerous_deserialization=True,
    )


def to_chunk(document: Document) -> dict:
    """LangChain Document -> the flat dict the prompt and logging layers expect."""
    return {**document.metadata, "answer": document.page_content}


def search(query: str, k: int = 3) -> list[tuple[dict, float]]:
    hits = _store().similarity_search_with_score(query, k=k)
    return [(to_chunk(doc), float(score)) for doc, score in hits]
