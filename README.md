# NovaCart Support Assistant

A multi-turn, RAG-grounded e-commerce customer support chatbot. FastAPI + Groq backend,
React + assistant-ui frontend, streamed over Server-Sent Events.

## Architecture

```
Browser (Vite/React, @assistant-ui/react)
  |  fetch POST /session            -> {session_id}
  |  fetch POST /chat (SSE)         -> event: token / event: done
  v
FastAPI (backend/app/main.py)
  |
  v
orchestrator.run_turn()  (backend/app/chat/orchestrator.py)
  1. retrieval (FAISS vector search -> TF-IDF fallback if low confidence)
  2. signals: sentiment (VADER) + topic tag from the retrieved chunk + "wants human"
  3. escalate only on a clear signal (see the escalation table below)
  4. otherwise stream a grounded reply from Groq (openai/gpt-oss-120b), guarding the
     literal ESCALATE sentinel so it's never leaked token-by-token to the client
  5. log every turn (SQLAlchemy: sessions / messages / feedback)
```

<img width="1880" height="2010" alt="Untitled-2025-03-13-1049" src="https://github.com/user-attachments/assets/42d18ab4-402c-4fbc-a3b2-73a1def8a486" />


The `/chat` endpoint streams `text/event-stream` frames: `event: token` for incremental
reply text, then one final `event: done` carrying `{message_id, escalated, human_offered,
intent, sentiment, sources}`. The frontend's custom `ChatModelAdapter` (`frontend/src/lib/
chatAdapter.ts`) parses this stream and feeds it into assistant-ui's `useLocalRuntime`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for a file-by-file breakdown of what each module does
and why.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate on cmd
pip install -r requirements.txt
cp .env.example .env            # then fill in GROQ_API_KEY from https://console.groq.com
python scripts/build_index.py   # parses data/kb/*.pdf -> FAISS index + data/kb_chunks.json
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive Swagger docs (also usable as a Postman
reference).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env            # VITE_API_BASE_URL defaults to http://localhost:8000
npm run dev
```

Visit `http://localhost:5173`.

### Tests

```bash
cd backend
python -m pytest tests/ -v
```

### Bonus scripts

```bash
python scripts/export_review_queue.py   # exports disliked (thumbs-down) messages to data/review_queue.json
```

## Requirement coverage

| Requirement | Implementation |
|---|---|
| Multi-turn conversation | `chat/session.py` replays the **whole** session from the DB, trimmed only by a character budget |
| Contextual memory in session | Full transcript passed into the grounded LLM prompt each turn, so facts from turn 1 survive to turn 20 |
| Answers only from FAQ set | RAG (FAISS + TF-IDF) + grounded system prompt + `ESCALATE` sentinel |
| Escalation to human | `orchestrator.run_turn` — see the escalation policy below |
| Greet and onboard | Prompt rule in `llm/prompts.py` — greets back, and answers in the same reply when the greeting came with a question |
| Order tracking / refund / technical / pricing | Dedicated sections across the KB PDFs, tagged into categories by `scripts/build_index.py` |
| Frustration / out-of-scope detection | VADER sentiment (`chat/sentiment.py`) + retrieval score threshold |
| Policy document set, raw + cleaned | Raw: 4 KB PDFs in `data/kb/` (includes a 50-question FAQ dataset). Cleaned: `data/kb_chunks.json`, the 124 chunks that were actually embedded |
| Embeddings + vector search | LangChain `HuggingFaceEmbeddings` (all-MiniLM-L6-v2) + LangChain `FAISS` store |
| Bonus: LangChain for RAG | Loader, splitter, embeddings and vector store are all LangChain (`scripts/build_index.py`, `rag/vector_store.py`) |
| Keyword lookup option | TF-IDF fallback (`rag/keyword_store.py`) when vector score is low |
| React frontend | Vite + React + `@assistant-ui/react` (`frontend/`) |
| Grounded, deterministic responses | Groq temperature 0.2 + strict grounded system prompt |
| Logging with timestamps | `Message` table (`db/models.py`), one row per turn |
| Feedback mechanism | Thumbs up/down (assistant-ui `FeedbackAdapter`) -> `Feedback` table |
| Bonus: feedback loop | `scripts/export_review_queue.py` |
| Bonus: sentiment detection | Surfaced in the `done` SSE event + logged per message |
| Bonus: mock customer profile | `profile/mock_profile.py`, personalizes greeting + order-tracking answers |
| Bonus: multi-user sessions | Sessions keyed by `session_id`; optional `user_id` for personalization |

### Escalation policy

Handing off to a human is deliberately rare: the bot answers first, and only escalates on a
clear signal that it isn't helping.

**Hard escalate** (handoff message + "Handed to agent" badge) — one trigger: the user asks for
a person outright ("connect me to a human", "talk to someone", "I want a real person"). Kept
as a regex in `chat/orchestrator.py` so it is honoured deterministically rather than left to
the model. The regex requires the *request framing*, not just the word: "is there a **human**
review step for damaged claims?" and "the courier **agent** left a note" are questions to
answer, not handoff requests.

**Soft offer** (answers normally, then offers a human):

- the user sounds unhappy — VADER compound < -0.5 (`chat/sentiment.py`). VADER's stock
  lexicon needed correcting in both directions before that threshold meant anything:
  - It **under-read complaints**: *"this is ridiculous, I've been waiting two weeks and
    nobody helps me"* scored **+0.03**, because "helps" is a positive word. The lexicon now
    carries the complaint terms that actually signal an unhappy customer — same message
    scores **-0.68**.
  - It **over-read ordinary questions**: "damaged" and "defective" score -0.44 *each*, so
    *"how do I return a defective item that arrived damaged?"* stacked to **-0.70** and
    looked angrier than "this is unacceptable". Words describing the **item's condition**
    are damped to near-neutral, because sentiment should measure the customer's mood, not
    the topic. Same message now scores **-0.25**.

  The result is a real gap to put a threshold in: routine questions top out around **-0.25**,
  genuine complaints start around **-0.57**. `tests/test_sentiment.py` locks both sides.
- the knowledge base genuinely doesn't cover it — the LLM returns the `ESCALATE` sentinel,
  which `llm/client.py` catches via its streaming buffer-guard so the literal word never
  reaches the user
- the model itself is unreachable (rate limit, timeout, or a reply truncated to zero
  tokens). The turn closes with a "try again in a moment" message plus the offer, so the
  client never renders an empty chat bubble

Being unable to answer one question, or one unhappy message, is **not** on its own a reason
to hand off. All thresholds live in `app/config.py`.

## Deviations from the original build spec

| Spec said | Built | Why |
|---|---|---|
| Model `llama-3.3-70b-versatile` | `openai/gpt-oss-120b` | Groq **retired** the Llama chat models; the id now returns HTTP 404 `model_not_found`. Verified against Groq's live `/models` endpoint. Still Groq — `gpt-oss` is an open-weights model Groq hosts, not a call to OpenAI. Swap it in `.env` — no code change needed. |
| Retrieval threshold 0.35 | 0.30 | 0.35 was too strict for short, casually-phrased questions and forced needless escalations. |
| `/chat` returns one JSON object | SSE token stream | Requested, for a live typing effect. The same structured payload still arrives as the final `event: done` frame. |
| React + plain fetch | React + `@assistant-ui/react` | Requested. Still Vite + React; `fetch` is used directly for all API calls. |
| Hand-written FAQ JSON dataset | 4 knowledge-base PDFs, chunked at build time | Richer and easier to extend — drop a PDF into `data/kb/`, rebuild, done. `data/kb_chunks.json` is the cleaned counterpart to the raw PDFs. |
| "Escalate when it cannot answer" | Answers plainly that it doesn't know, then **offers** a human (`escalated=false`, `human_offered=true`) | Deliberate. Auto-escalating every unanswerable question meant trivia like "tell me a joke" produced a "Handed to agent" handoff. A person is still one message away — the reply invites it, and asking for one escalates immediately. Flip `human_offered` to `escalated` in `orchestrator.run_turn`'s `cannot_answer` branch to get the literal spec behaviour. |

## Groq free-tier quotas and model choice

The free tier caps **tokens per day (TPD) at 200,000 per model**. That budget is what decides
which model this project runs, and the deciding factor is *reasoning tokens*.

Measured on the same question ("what is your return policy?"), same prompt:

| Model | Reasoning tokens | Total/turn | Turns/day on 200k |
|---|---|---|---|
| `qwen/qwen3.6-27b` | **800** | 1,792 | ~111 |
| `openai/gpt-oss-120b` | **65** | 1,275 | ~156 |

`qwen3.6-27b` is a *reasoning* model: it spends ~800 hidden tokens thinking before writing a
two-sentence support answer. Those tokens count against the quota and delay the first
streamed token. Running the test suites drained the daily budget, and once exhausted Groq
stops returning text — sometimes as HTTP 429, sometimes by silently truncating the reply to
zero content tokens (`finish_reason: "length"`), which is what produced blank chat bubbles.

`openai/gpt-oss-120b` does the same job with **~12x less reasoning**, so it is the default.

Both failure modes are still handled defensively: the client retries (honouring
`Retry-After`), and any turn that still produces no text falls through to the
service-unavailable reply rather than an empty bubble. If you exhaust one model mid-demo,
every model has its own quota — switch in `.env`, no code change:

```
GROQ_MODEL=qwen/qwen3.6-27b
```

**Grounding note.** `gpt-oss-120b` was initially looser than qwen about answering from
general knowledge — it once claimed "NovaCart ships to many international destinations",
which appears nowhere in the knowledge base. That was fixed in the prompt rather than by
paying 800 tokens/turn: `llm/prompts.py` now requires every factual claim to come from
CONTEXT, states that partially-relevant CONTEXT is not permission to answer the rest from
memory, and makes the `ESCALATE` sentinel unambiguous (the model was writing its own
out-of-scope refusal instead of emitting the sentinel, which silently bypassed the
human-offer path). Verified: both "do you ship internationally?" and "do you have a loyalty
programme?" now decline instead of inventing.

## Frontend scope

The UI was scaffolded from assistant-ui's full template, which ships renderers for
attachments, images, files, tool calls and reasoning. This assistant streams **plain text
only** — `lib/chatAdapter.ts` yields nothing but `{type: "text"}` parts, and the backend
returns no other part type — so those renderers were unreachable code and have been removed
(9 files, ~2,500 lines), along with the `thread.tsx` wiring and the npm packages that only
served them.

What remains under `frontend/src/components/`:

| File | Role |
|---|---|
| `thread.tsx` | Chat viewport, composer, user message, edit/branch controls |
| `support-assistant-message.tsx` | Assistant bubble: markdown, "Handed to agent" badge, thumbs up/down |
| `markdown-text.tsx` | Renders `**bold**` etc. instead of printing literal asterisks |
| `session-badge.tsx` | Copyable session id in the header |
| `help-panel.tsx` | In-app usage guide |
| `tooltip-icon-button.tsx`, `ui/` | Button, dialog, tooltip primitives |

`npm run build` is the regression test for this: it fails on any dangling import.
