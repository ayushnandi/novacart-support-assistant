# Architecture — every file, what it does, and why it exists

File-by-file reference for `backend/app/`. A full symbol-usage audit was run: every function
and constant listed here has a live caller. Dead code found along the way is listed at the
bottom with what happened to it.

**895 lines of Python across 15 modules.**

---

## Request flow (one chat turn)

```
Browser (React + assistant-ui)
  │  POST /session  ──► {session_id}                      (once, on page load)
  │  POST /chat     ──► SSE: event:token … event:done     (per message)
  ▼
main.py  ── _stream_chat() wraps the orchestrator as SSE frames
  ▼
chat/orchestrator.py  run_turn()      ◄── the brain; everything below is called from here
  ├─ chat/session.py   get_history()          last 6 turns, for context
  ├─ rag/retriever.py  retrieve()             FAISS → TF-IDF fallback
  ├─ chat/sentiment.py score()                VADER tone
  ├─ llm/prompts.py    build_messages()       grounded system prompt + history
  ├─ llm/client.py     stream_grounded_reply() Groq stream + ESCALATE guard
  └─ db/crud.py        log_message()          every turn persisted
```

---

## `app/chat/` — conversation logic (247 lines)

### `orchestrator.py` (217 lines)
The brain. `run_turn(session_id, message, user_id)` is an **async generator** yielding
`("token", …)` frames as text streams in, then exactly one `("done", …)` frame carrying
`message_id`, `escalated`, `human_offered`, `intent`, `sentiment`, `sources`.

`run_turn` is the **only** symbol used outside this file (`main.py`, tests). Everything else
is private:

| Symbol | Purpose |
|---|---|
| `HUMAN_REQUEST_PATTERN` | Regex for "human / agent / representative / talk to someone". Stays explicit Python rather than a prompt rule because an outright request for a person must be honoured deterministically, not left to the model's judgement. |
| `_retrieve_in_context()` | Retries retrieval with the previous question attached when the first attempt scores under threshold — see *Follow-up questions* below. |
| `_handoff_message()` | The "connecting you to a human" text, with the user's message quoted so they don't repeat themselves. |
| `_no_answer_message()` | Used when the KB genuinely doesn't cover the question. |
| `HUMAN_OFFER_LINE` | Appended to a normal answer when the user sounds unhappy. |
| `_log_user_message()` / `_log_assistant_message()` | Persist each turn. |

**No intent classifier.** The retrieved chunk already carries a `category` assigned at build time,
so the topic tag is read straight off the top hit (`out_of_scope` when retrieval is weak). A
separate keyword classifier used to exist; it duplicated the KB's own categorisation and
drifted out of step with it, so it was deleted.

**Greetings are handled by the prompt, not by Python.** An earlier version had
`has_greeting` / `strip_greeting` / `is_greeting` plus a filler-word list. That was ~40 lines
of hand-rolled parsing whose prefix matching once swallowed real questions
(*"hello can i know where is my order"* → canned welcome). One prompt rule does it better.

### `session.py` (17 lines)
`get_history(session_id)` — the last `SESSION_HISTORY_TURNS × 2` messages as OpenAI-style
`{role, content}` dicts. This is what makes multi-turn recall work ("what is my name" →
"Ayush") and what `_retrieve_in_context` uses to rescue follow-ups.

### `sentiment.py` (9 lines)
`score(text)` — VADER compound, −1 to +1. Called once per turn; the value is logged on every
message and decides whether the reply offers a human. Satisfies the assignment's
"identify when the user is frustrated" requirement and the sentiment-detection bonus.

---

## Escalation policy

Handing off is deliberately **rare** — the bot answers first.

**Hard escalate** (handoff message + "Handed to agent" badge) — one trigger: the user asks for
a person outright.

**Soft offer** (answers normally, then offers a human):
- the user sounds unhappy — VADER < `SENTIMENT_NEGATIVE_THRESHOLD` (−0.2)
- the KB doesn't cover the question — the LLM returns the `ESCALATE` sentinel

Being unable to answer one question, or one unhappy message, is **not** a reason to hand off.
Earlier versions escalated on tone alone and on repeat-count, and both fired far too eagerly.

---

## `app/rag/` — retrieval (226 lines)

Built on **LangChain**. The pieces LangChain owns:

| Stage | LangChain component |
|---|---|
| Load PDFs | `PyPDFDirectoryLoader` (`langchain_community`) |
| Chunk | `RecursiveCharacterTextSplitter` (`langchain_text_splitters`) |
| Embed | `HuggingFaceEmbeddings` (`langchain_huggingface`) wrapping `all-MiniLM-L6-v2` |
| Vector store | `FAISS` (`langchain_community`), `MAX_INNER_PRODUCT` distance |
| Chunk record | `langchain_core.documents.Document` |

| File | Role |
|---|---|
| `vector_store.py` | Wraps the LangChain FAISS store: `build()`, `search()` (returns `(chunk, score)`), and `to_chunk()` which flattens a `Document` into the dict the prompt/logging layers expect. Embeddings and store are `@lru_cache`d so the model loads once. |
| `keyword_store.py` | TF-IDF + cosine over `data/kb_chunks.json` — the same corpus the index was built from. Same `search()` signature as the vector store. |
| `retriever.py` | `retrieve()` — FAISS first; if the top score is below `RETRIEVAL_SCORE_THRESHOLD` (0.30), falls back to TF-IDF and reports `max(vector, keyword)`. Returns `RetrievalResult(faqs, max_score)`. |

Embeddings are L2-normalised and the store uses inner-product distance, so scores are cosine
in the 0..1 range the threshold is tuned against (e.g. *"how do i track my order"* → **0.692**,
*"what is the meaning of life"* → **0.112**).

Section headings are still detected in `scripts/build_index.py` before splitting, so each
chunk keeps a meaningful `question` and a `category` in its metadata — LangChain's splitter
then handles size within each section.

**The TF-IDF fallback is not dead code.** It runs on every query where FAISS scores under
0.30 — typically vague or out-of-scope wording — and can lift a query back over the
threshold. It's also an explicit assignment requirement ("vector search **or** keyword-based
lookup").

### Knowledge base
The corpus is the four PDFs in `backend/data/kb/` — **124 chunks** covering order tracking and
delivery, customer-service and escalation paths, the complete support policy set, and the
agent/FAQ dataset. `python scripts/build_index.py` re-parses them and rewrites the index.

The PDFs are the single editable source: drop another one into `data/kb/`, rerun the build,
and the bot knows it — no code change needed. The build also writes `data/kb_chunks.json`, the
readable cleaned counterpart to the raw PDFs (and what the TF-IDF fallback loads).

### Follow-up questions
`_retrieve_in_context()` handles messages with nothing retrievable in them on their own.
*"i am not able to view that option"* scores **0.224** and would be written off as
out-of-scope; retried with the previous user message attached it scores **0.558** and pulls
the right order-tracking chunks. No extra LLM call, and it only runs when the first attempt is
weak.

---

## `app/llm/` — model layer (108 lines)

### `client.py`
Groq via the `openai` SDK (`base_url` swap keeps the provider replaceable). Temperature 0.2.

The important part is **`stream_grounded_reply()`** and its sentinel guard. The prompt tells
the model to reply with exactly `ESCALATE` when it can't answer — but with streaming that
would flash `ESC` `AL` `ATE` on screen before the server could react. So the first ~15
characters are buffered: if they resolve to exactly `ESCALATE`, the buffer is discarded and an
escalate event is emitted instead; otherwise the buffer is flushed and the rest streams live.
Real answers diverge within a few characters, so there's no perceptible delay.

Two call-level details needed to make Groq behave:
- `tool_choice="none"` — some Groq models spontaneously emit tool calls and crash the stream
  with `Tool choice is none, but model called a tool`.
- `reasoning_format="hidden"` — keeps chain-of-thought out of `content`, so `<think>` blocks
  never reach the user.

`stream_completion()` is the raw delta iterator; `stream_grounded_reply()` is the only caller.

### `prompts.py`
`build_system_prompt(context_chunks)` and `build_messages(...)`. Two rule blocks:
- **GROUNDING** — answer only from CONTEXT; may recall what the user said earlier; never
  invent policies/prices/dates; ask a clarifying question rather than refusing when the ask is
  vague; reply `ESCALATE` only when nothing is relevant; never mention transfers or human
  agents (the orchestrator owns that).
- **STYLE** — greet back when greeted; 2–4 sentences; bullets only for multi-step answers;
  bold the key figure; answer first without restating the question.

---

## `app/db/` — persistence (127 lines)

| File | Role |
|---|---|
| `models.py` | `Session`, `Message` (role, content, intent, sentiment, escalated, sources_json, created_at), `Feedback` (message_id, rating, comment). UUID primary keys via `_uuid()`. |
| `crud.py` | `create_session`, `log_message`, `get_messages`, `save_feedback`, `get_disliked_messages`. |
| `database.py` | Engine, `SessionLocal`, and the `get_db` FastAPI dependency. |

Every user message and assistant reply is logged with a timestamp — the assignment's logging
requirement. `sources_json` keeps the retrieved chunk ids per message for auditing; the data
is in the API response and the DB, it's just not rendered in the chat bubble (retrieval always
returns the top 3 whether or not the answer used them, so showing them implied a precision
that wasn't real).

`get_disliked_messages` has exactly one caller: `scripts/export_review_queue.py`, the bonus
feedback loop.

---

## `app/main.py` — API surface (91 lines)

| Endpoint | Called by | Purpose |
|---|---|---|
| `POST /session` | frontend | Create a session, return its id |
| `POST /chat` | frontend | SSE stream of the turn |
| `POST /feedback` | frontend | Thumbs up/down |
| `GET /health` | Postman / ops | Liveness check |
| `GET /logs?session_id=` | Postman / demo | Full transcript with intent, sentiment, escalation, sources |
| `GET /profile/{user_id}` | Postman / demo | Mock customer profile |

The last three have **no frontend caller** — intentional. `/logs` demonstrates the logging
requirement, `/profile` the mock-profile bonus, and both are in the Postman collection. Note
`get_profile` is also used server-side by the orchestrator for personalised answers.

CORS uses `allow_origin_regex=r"^http://localhost:\d+$"` so Vite can pick any free port across
restarts without breaking the browser.

---

## Supporting modules

| Path | Role |
|---|---|
| `app/config.py` | All tunables in one place: model/keys, paths, thresholds, `STORE_NAME`, `ESCALATE_SENTINEL`. Every constant is referenced. |
| `app/pydantic_models.py` | Request/response schemas. All six are bound to routes in `main.py`. |
| `app/profile/mock_profile.py` | Fake customer profiles (`ayush`, `demo`) + a default fallback. Used by `/profile` and by the orchestrator's personalisation branch. |
| `data/kb/*.pdf` | The four NovaCart knowledge-base PDFs — the source of everything the bot knows. |
| `scripts/build_index.py` | Parses `data/kb/*.pdf` and rebuilds the index. Run before first start, and after changing the PDFs. |
| `scripts/export_review_queue.py` | Exports thumbs-down messages to `data/review_queue.json` — the bonus feedback loop. |
| `tests/` | 6 tests: escalation policy (4) and retrieval (2). |

---

## Frontend (`frontend/src/`)

| File | Role |
|---|---|
| `App.tsx` | Wires `useLocalRuntime` + `AssistantRuntimeProvider`; header with session id and demo user id. |
| `lib/api.ts` | `getSessionId`, `streamChat` (manual SSE parsing over `fetch` — `EventSource` can't POST), `submitFeedback`. |
| `lib/chatAdapter.ts` | `ChatModelAdapter.run()` — async generator feeding streamed text into assistant-ui, attaching `escalated` / `humanOffered` / `messageId` as message metadata. |
| `lib/feedbackAdapter.ts` | Maps assistant-ui's positive/negative to the `/feedback` API. |
| `components/support-assistant-message.tsx` | Custom assistant bubble: markdown rendering, escalation badge, thumbs with selected state. |
| `components/help-panel.tsx`, `session-badge.tsx` | In-app usage guide; copyable session id. |
| `components/thread.tsx` + `ui/` | Generated by `npx assistant-ui@latest init` — stock components, kept as-is. |

---

## What was removed, and why

Successive audits stripped the codebase down. Nothing below has a caller left anywhere.

| Round | Removed | Reason |
|---|---|---|
| 1 | `is_new_session()`, `RetrievalResult.scores` / `.source`, unused `json` / `Path` / `numpy` / `SessionLocal` imports | Zero references |
| 2 | `has_greeting`, `strip_greeting`, `is_greeting`, `_GREETING_FILLER`, `_TRIM_CHARS`, `GREETING_REPLY`, `_greeting_text`, the `greet` prompt param | ~60 lines of hand-rolled greeting parsing replaced by one prompt rule |
| 2 | `wants_human()` + its 6-pattern list | Folded into a single `HUMAN_REQUEST_PATTERN` regex |
| 3 | `data/faqs_clean.json`, `data/faqs_raw.json` | Replaced by the KB PDFs; chunks now live in the index, so there's no dataset file to keep in sync |
| 4 | `app/chat/intent.py` (whole file), `count_repeats()`, `REPEAT_*` constants | The KB supplies categories; repeat-based escalation triggers dropped |
| 5 | `is_frustrated()`, `SENTIMENT_FRUSTRATION_THRESHOLD` | **Dead logic**: `frustrated` (< −0.5) was OR'd with `< −0.2`, a strictly looser test, so it could never change the outcome — and it made VADER run twice per message |

**Kept deliberately**, despite looking unused: the TF-IDF fallback (spec-required *and*
genuinely reached), `/logs` + `/profile` + `/health`, and `get_disliked_messages` with its
export script.
