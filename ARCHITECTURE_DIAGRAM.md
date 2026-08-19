# NovaCart Support Assistant — Architecture

Multi-turn, RAG-grounded e-commerce support assistant.
FastAPI + LangChain/FAISS + Groq backend, React (`@assistant-ui/react`) frontend,
answers streamed over Server-Sent Events, every turn logged to SQLite.

---

## 1. System overview

```
 +--------------------------------------------------------------------------+
 |  BROWSER   Vite + React + @assistant-ui/react            http://:5173    |
 |                                                                          |
 |   App.tsx ............ session bootstrap, demo user id, thread           |
 |   lib/api.ts ......... fetch + manual SSE parsing                        |
 |   lib/chatAdapter.ts . feeds streamed tokens into useLocalRuntime        |
 |   lib/feedbackAdapter  thumbs up / down -> POST /feedback                |
 +--------------------------------------------------------------------------+
        |                       ^
        |  POST /session        |  {"session_id": "..."}          (once, on load)
        |  POST /chat           |  event: token  {"text": "..."}  (many)
        |                       |  event: done   {message_id, escalated,
        |                       |                 human_offered, intent,
        |                       |                 sentiment, sources}
        |  POST /feedback       |  {"ok": true}
        v                       |
 +--------------------------------------------------------------------------+
 |  FASTAPI   backend/app/main.py                           http://:8000    |
 |  Swagger UI at /docs   |   CORS: localhost on any port                   |
 |                                                                          |
 |  POST /session   POST /chat (SSE)   POST /feedback                       |
 |  GET  /health    GET  /logs         GET  /profile/{user_id}              |
 +--------------------------------------------------------------------------+
        |
        v
 +--------------------------------------------------------------------------+
 |  ORCHESTRATOR   app/chat/orchestrator.py :: run_turn()                   |
 |  async generator -> ("token", ...) * N  then exactly one ("done", ...)   |
 +--------------------------------------------------------------------------+
     |            |             |              |              |
     v            v             v              v              v
 +---------+  +-----------+  +-----------+  +-----------+  +-----------+
 | session |  | retriever |  | sentiment |  | prompts   |  | db/crud   |
 | .py     |  | .py       |  | .py       |  | + client  |  | .py       |
 |         |  |           |  |           |  |           |  |           |
 | replays |  | FAISS ->  |  | VADER     |  | grounded  |  | log user  |
 | whole   |  | TF-IDF    |  | compound  |  | system    |  | + reply,  |
 | session |  | fallback  |  | -1 .. +1  |  | prompt,   |  | feedback  |
 | (8k     |  | top k = 3 |  |           |  | temp 0.2  |  |           |
 |  chars) |  | thr 0.30  |  | thr -0.5  |  | ESCALATE  |  |           |
 +---------+  +-----------+  +-----------+  |  guard    |  +-----------+
                   |                        +-----------+       |
                   v                              |             v
        +----------------------+       +---------------------+  +-----------+
        | app/rag/index/       |       | GROQ  (OpenAI SDK,  |  | SQLite    |
        |   kb.faiss, kb.pkl   |       |  base_url swapped)  |  | app.db    |
        | data/kb_chunks.json  |       | qwen/qwen3.6-27b    |  | sessions  |
        | 124 chunks           |       | temperature 0.2     |  | messages  |
        +----------------------+       +---------------------+  | feedback  |
                                                                +-----------+
```

---

## 2. One chat turn, step by step

```
  user types "where is my order?"
        |
        v
 [1] get_history(session_id)          <- whole transcript from SQLite,
        |                                trimmed only by HISTORY_CHAR_BUDGET (8000 chars).
        |                                Empty + outage messages filtered out.
        v
 [2] log the user message             <- timestamped row in `messages`
        |
        v
 [3] sentiment.score(message)         <- VADER compound, logged on every turn
        |
        v
 [4] retrieval  ---------------------------------------------------------+
        |                                                                |
        |   embed query (all-MiniLM-L6-v2, L2-normalised)                |
        |             |                                                  |
        |             v                                                  |
        |   FAISS inner-product search, top 3  --> max_score             |
        |             |                                                  |
        |     max_score >= 0.30 ? ----- yes --> use these chunks         |
        |             |                                                  |
        |             no                                                 |
        |             |                                                  |
        |             v                                                  |
        |   retry with previous user message prepended                   |
        |   ("i am not able to view that option": 0.224 -> 0.558)        |
        |             |                                                  |
        |     still low ? --> TF-IDF keyword search over                 |
        |                     data/kb_chunks.json, report                |
        |                     max(vector, keyword)                       |
        +----------------------------------------------------------------+
        |
        v
 [5] intent = category of the top chunk, or "out_of_scope" if score < 0.30
        |
        v
 [6] ESCALATION DECISION  (see section 3)
        |
        +-- hard escalate --> handoff message, escalated=true, done. No LLM call.
        |
        v
 [7] build grounded prompt: system rules + retrieved CONTEXT + full history
        |    (+ mock customer profile injected when user_id is set and the
        |     topic is order_tracking)
        v
 [8] Groq stream, temperature 0.2
        |    first ~15 chars buffered: if they resolve to exactly "ESCALATE",
        |    the buffer is dropped and a cannot-answer event is raised instead,
        |    so the sentinel never flashes on screen token by token.
        v
 [9] tokens streamed to the browser as `event: token`
        |
        v
[10] log the assistant reply (intent, sentiment, escalated, sources_json)
        |
        v
[11] `event: done` -> message_id, escalated, human_offered, intent,
                      sentiment, sources
```

---

## 3. Escalation policy

Handing off is deliberately rare: the bot answers first, and only escalates on a clear
signal. Thresholds live in `app/config.py`.

```
                        incoming user message
                                 |
                                 v
              +----------------------------------------+
              | HUMAN_REQUEST_PATTERN matches?          |
              | "connect me to a human", "talk to       |
              |  someone", "I want a real person"       |
              | (regex, not the model, so it is         |
              |  honoured deterministically)            |
              +----------------------------------------+
                    | yes                     | no
                    v                         v
        HARD ESCALATE                +---------------------------+
        escalated = true             | LLM returned the          |
        handoff text quoting         | ESCALATE sentinel?        |
        the user message             | (KB does not cover it)    |
        "Handed to agent" badge      +---------------------------+
        no LLM call                        | yes           | no
                                           v               v
                                  SOFT OFFER          +------------------+
                                  plain "I don't      | VADER compound   |
                                  have that" +        | < -0.5 ?         |
                                  offer a human       +------------------+
                                  escalated = false      | yes      | no
                                  human_offered = true   v          v
                                                    SOFT OFFER   NORMAL
                                                    real answer  grounded
                                                    + offer line  answer
```

Also a soft offer: the model is unreachable (429 / timeout / reply truncated to zero
tokens). The turn closes with a "try again in a moment" message so the client never
renders an empty bubble; that reply is tagged `service_error` and filtered out of the
next turn's context.

Why VADER needed tuning before `-0.5` meant anything:

```
  message                                        stock VADER    tuned lexicon
  ---------------------------------------------  -----------    -------------
  "this is ridiculous, I've been waiting two          +0.03         -0.68
   weeks and nobody helps me"                      (missed)       (caught)

  "how do I return a defective item that              -0.70         -0.25
   arrived damaged?"                            (false alarm)    (ignored)

  routine questions now top out ~ -0.25 | real complaints start ~ -0.57
                          threshold -0.5 sits in the gap
```

---

## 4. Build-time indexing (raw -> cleaned -> embedded)

```
  backend/data/kb/*.pdf              RAW: 4 NovaCart knowledge-base PDFs
    NovaCart_Customer_Service_Support_Knowledge_Base.pdf
    NovaCart_Order_Tracking_Knowledge_Base.pdf
    NovaCart_Support_AI_Agent_Knowledge_Base.pdf        (50-question FAQ set)
    NovaCart_Support_Complete_Knowledge_Base.pdf
        |
        |  python scripts/build_index.py
        v
  PyPDFDirectoryLoader            (langchain_community)
        |
        v
  section-heading detection  -> each chunk keeps `question` + `category`
        |
        v
  RecursiveCharacterTextSplitter  (langchain_text_splitters)
        |
        +--------------------------------+
        v                                v
  HuggingFaceEmbeddings           data/kb_chunks.json
  all-MiniLM-L6-v2                CLEANED: the 124 chunks actually embedded,
        |                         human-readable, and the corpus the
        v                         TF-IDF fallback loads at runtime
  FAISS (MAX_INNER_PRODUCT)              |
        |                                v
        v                         TfidfVectorizer + cosine
  app/rag/index/kb.faiss          (rag/keyword_store.py)
  app/rag/index/kb.pkl
```

Drop another PDF into `data/kb/`, rerun `build_index.py`, and the bot knows it. No code
change.

---

## 5. Data model

```
  sessions                messages                        feedback
  --------                --------                        --------
  id (uuid)  1 -------< id (uuid)         1 ----------< id (uuid)
  user_id               session_id (fk)                  message_id (fk)
  created_at            role  user|assistant             rating  up|down
                        content                          comment
                        intent                           created_at
                        sentiment  float
                        escalated  bool
                        sources_json
                        created_at   <- the timestamped log
```

---

## 6. Module legend

| Module | Role |
|---|---|
| `app/main.py` | FastAPI app; wraps `run_turn` as SSE frames; 6 endpoints |
| `app/config.py` | Every tunable in one place: model, paths, thresholds, sentinel |
| `app/chat/orchestrator.py` | The brain — retrieve, score, decide, stream, log |
| `app/chat/session.py` | Replays the whole session within an 8000-char budget |
| `app/chat/sentiment.py` | VADER compound score per user message |
| `app/rag/retriever.py` | FAISS first, TF-IDF fallback below 0.30, returns top 3 |
| `app/rag/vector_store.py` | LangChain FAISS store: `build()`, `search()`, `to_chunk()` |
| `app/rag/keyword_store.py` | TF-IDF + cosine over `kb_chunks.json` |
| `app/llm/client.py` | Groq via the OpenAI SDK; streaming + ESCALATE buffer guard |
| `app/llm/prompts.py` | Grounding rules + style rules + CONTEXT + history |
| `app/db/models.py`, `crud.py` | Sessions, messages, feedback; log and query helpers |
| `app/profile/mock_profile.py` | Mock customer profiles for personalised answers |
| `scripts/build_index.py` | PDFs -> chunks -> FAISS index + `kb_chunks.json` |
| `scripts/export_review_queue.py` | Thumbs-down messages -> `data/review_queue.json` |

---

## 7. Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.10+), Uvicorn |
| RAG | LangChain: PyPDFDirectoryLoader, RecursiveCharacterTextSplitter, HuggingFaceEmbeddings, FAISS |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers, CPU) |
| Keyword fallback | scikit-learn TF-IDF |
| LLM | Groq `qwen/qwen3.6-27b` via the `openai` SDK, temperature 0.2 |
| Sentiment | vaderSentiment, tuned lexicon |
| Storage | SQLite via SQLAlchemy |
| Frontend | Vite + React + `@assistant-ui/react`, SSE over `fetch` |
| Testing | pytest (28 tests) + Postman collection |
