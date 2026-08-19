"""Parse the knowledge-base PDFs into a FAISS index (LangChain) + a readable chunk dump."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import INDEX_DIR, KB_CHUNKS_PATH, KB_DIR
from app.rag import vector_store

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# Section heading lines look like "3. Refunds & Cancellations".
_HEADING = re.compile(r"^\s*\d+(\.\d+)*\.?\s+[A-Z][^\n]{2,80}$")
_PAGE_NOISE = re.compile(r"^\s*(Page \d+.*|NovaCart Support.*Page \d+)\s*$", re.IGNORECASE)

# Heading keyword -> the categories used for logging and personalisation.
_CATEGORY_RULES = [
    ("order_tracking", ("track", "delivery", "shipment", "courier", "order status")),
    ("refund_cancellation", ("refund", "cancel")),
    ("returns_exchanges", ("return", "exchange", "replacement")),
    ("payments_pricing", ("payment", "pricing", "price", "coupon", "billing", "charge")),
    ("shipping", ("shipping", "dispatch")),
    ("account_subscription", ("account", "subscription", "membership", "plus", "login")),
    ("technical_support", ("technical", "troubleshoot", "app", "website", "error")),
    ("escalation", ("escalat", "human", "agent", "contact", "customer service", "support option")),
]


def _categorise(heading: str) -> str:
    lowered = heading.lower()
    for category, needles in _CATEGORY_RULES:
        if any(n in lowered for n in needles):
            return category
    return "general"


def _clean(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln.strip() and not _PAGE_NOISE.match(ln))


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Group the document into (heading, body) pairs on its numbered headings."""
    sections: list[tuple[str, list[str]]] = []
    heading, buffer = "Overview", []

    for line in text.splitlines():
        if _HEADING.match(line):
            if buffer:
                sections.append((heading, buffer))
            heading, buffer = line.strip(), []
        else:
            buffer.append(line)
    if buffer:
        sections.append((heading, buffer))

    return [(h, "\n".join(b).strip()) for h, b in sections if "\n".join(b).strip()]


def build_documents() -> list[Document]:
    pages = PyPDFDirectoryLoader(str(KB_DIR)).load()
    if not pages:
        raise FileNotFoundError(f"No knowledge-base PDFs found in {KB_DIR}")

    # PyPDFDirectoryLoader yields one Document per page; stitch each file back together
    # so section headings that span a page break still group correctly.
    by_file: dict[str, list[str]] = {}
    for page in pages:
        name = Path(page.metadata.get("source", "unknown")).name
        by_file.setdefault(name, []).append(page.page_content or "")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    documents: list[Document] = []
    for name, page_texts in sorted(by_file.items()):
        for heading, body in _split_sections(_clean("\n".join(page_texts))):
            for part in splitter.split_text(body):
                documents.append(
                    Document(
                        page_content=part,
                        metadata={
                            "id": len(documents) + 1,
                            "source": name,
                            "category": _categorise(heading),
                            "question": heading,
                        },
                    )
                )
    return documents


def main() -> None:
    documents = build_documents()
    vector_store.build(documents)

    # Readable counterpart to the raw PDFs: the cleaned, chunked corpus that was embedded.
    # The app reads the index, not this file - it exists so the dataset can be inspected.
    chunks = [vector_store.to_chunk(d) for d in documents]
    with open(KB_CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    for source, count in sorted(Counter(c["source"] for c in chunks).items()):
        print(f"  {count:3d} chunks  {source}")
    print(f"Indexed {len(chunks)} chunks -> {INDEX_DIR}")
    print(f"Cleaned dataset written to {KB_CHUNKS_PATH}")


if __name__ == "__main__":
    main()
