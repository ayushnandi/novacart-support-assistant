import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# gpt-oss-120b over qwen3.6-27b: qwen is a reasoning model and spends ~800 hidden reasoning
# tokens on a two-sentence support answer, which burns Groq's 200k/day free tier in ~111
# turns and delays the first streamed token. gpt-oss-120b uses ~73 for the same answer.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

DATA_DIR = BASE_DIR / "data"
KB_DIR = DATA_DIR / "kb"  # raw knowledge-base PDFs the RAG index is built from
KB_CHUNKS_PATH = DATA_DIR / "kb_chunks.json"  # cleaned, chunked version of those PDFs
INDEX_DIR = BASE_DIR / "app" / "rag" / "index"
REVIEW_QUEUE_PATH = DATA_DIR / "review_queue.json"

DATABASE_URL = f"sqlite:///{BASE_DIR / 'app.db'}"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
RETRIEVAL_TOP_K = 3
RETRIEVAL_SCORE_THRESHOLD = 0.30

# The assistant keeps the whole conversation, not a fixed number of turns - asking "what did
# I ask you first?" should work the way it does in any chat app. The only limit is size: once
# the transcript would crowd out the prompt, the oldest messages are dropped. Measured in
# characters (~4 per token), so this is roughly 2,000 tokens of history.
HISTORY_CHAR_BUDGET = 8000

# VADER compound below this = the user sounds unhappy, so the reply also offers a human.
# Tuned from measured scores, not guessed: ordinary support questions carry topic words that
# read as negative on their own ("damaged", "defective", "cancel") and bottom out around
# -0.44, while real complaints start around -0.57. -0.5 sits in that gap, so asking about a
# damaged item doesn't trigger a handoff offer but "this is unacceptable" does.
SENTIMENT_NEGATIVE_THRESHOLD = -0.5

STORE_NAME = "NovaCart"
ESCALATE_SENTINEL = "ESCALATE"
