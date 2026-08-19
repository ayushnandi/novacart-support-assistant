# Demo video script — NovaCart Support Assistant (Assignment 103)

**Runtime: 6:30.** Voiceover + screen recording. Read the "Say" column out loud; do what
the "Show" column says at the same time.

---

## Before you hit record

| # | Check | Command / action |
|---|---|---|
| 1 | Backend venv active | `cd backend && source .venv/Scripts/activate` |
| 2 | Model is alive today | `curl -s -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models \| grep qwen` — if the daily quota is gone, set `GROQ_MODEL=openai/gpt-oss-120b` in `.env` |
| 3 | Fresh log DB so `/logs` is clean | rename `backend/app.db` to `app.db.bak` (it is recreated on start) |
| 4 | Warm the model cache | send one throwaway chat message, then reload the page — the very first query loads `all-MiniLM-L6-v2` and takes a few seconds |
| 5 | Screen setup | Terminal 1 (backend) + Terminal 2 (scripts) + browser, all at ~125% zoom, dark or light consistently |
| 6 | Browser tabs pre-opened | `localhost:5173` (frontend) and `localhost:8000/docs` (Swagger) |
| 7 | Editor tab open | `ARCHITECTURE_DIAGRAM.md` in preview, scrolled to section 1 |

Two things worth knowing while recording: `pytest` makes real Groq calls (4 of the 28
tests hit the model), so run the test segment **last**; and the KB rebuild takes ~30–60s,
so plan a jump cut there.

---

## Segment 0 — Hook (0:00 – 0:25)

| Time | Say | Show |
|---|---|---|
| 0:00 | "This is NovaCart Support — a multi-turn conversational assistant for e-commerce customer service, built for Assignment 103." | Frontend at `localhost:5173`, chat empty, header visible |
| 0:08 | "It answers only from a fixed knowledge base using retrieval-augmented generation, it remembers the whole conversation, it detects when a customer is frustrated, and it hands off to a human when it should." | Slow scroll over the empty thread and the header (session id badge, demo user id field) |
| 0:18 | "FastAPI and LangChain on the backend, React on the front, Groq for the model, everything logged to SQLite. Let me show you how it's put together, then run it end to end." | Hold on the UI |

---

## Segment 1 — Architecture (0:25 – 1:05)

| Time | Say | Show |
|---|---|---|
| 0:25 | "The browser is a Vite React app using assistant-ui. On load it calls POST /session for a session id, and every message goes to POST /chat, which streams the answer back over Server-Sent Events — token events while the reply is being written, then one done event carrying the message id, the escalation flags, the intent, and the sentiment score." | `ARCHITECTURE_DIAGRAM.md`, section 1, top half |
| 0:40 | "On the server, every turn runs through one function: `run_turn` in the orchestrator. It pulls the conversation history, retrieves from the knowledge base, scores the sentiment, builds a grounded prompt, streams the model's answer, and logs the whole thing." | Scroll to the orchestrator box and the five modules under it |
| 0:53 | "Retrieval is FAISS vector search over 124 chunks, with a TF-IDF keyword fallback whenever the vector score drops below 0.30. The model is Groq at temperature 0.2, and the prompt is strict: answer only from the retrieved context, and if the context doesn't have it, reply with the literal word ESCALATE." | Scroll to the FAISS / Groq / SQLite boxes at the bottom |

---

## Segment 2 — The dataset: raw and cleaned (1:05 – 1:50)

| Time | Say | Show |
|---|---|---|
| 1:05 | "The assignment asks for a policy document set in both raw and cleaned form. The raw side is four NovaCart knowledge-base PDFs — customer service, order tracking, the complete policy set, and a fifty-question FAQ dataset." | Terminal 2: `ls backend/data/kb/` |
| 1:16 | "One script turns them into the cleaned, embedded corpus. LangChain loads the PDFs, detects section headings so every chunk keeps its own question and category, splits them, embeds them with all-MiniLM-L6-v2, and writes a FAISS index." | Run `python scripts/build_index.py` |
| 1:30 | "124 chunks indexed. It also writes kb_chunks.json — that's the cleaned dataset, human-readable, and it's the same corpus the TF-IDF fallback searches at runtime." | *(jump cut past the build)* Show the final `Indexed 124 chunks` lines, then open `data/kb_chunks.json` and scroll a few entries |
| 1:42 | "Adding knowledge means dropping another PDF in that folder and rerunning this. No code changes." | Hold on `kb_chunks.json` |

---

## Segment 3 — Start the API (1:50 – 2:10)

| Time | Say | Show |
|---|---|---|
| 1:50 | "Backend is FastAPI." | Terminal 1: `uvicorn app.main:app --reload --port 8000` |
| 1:56 | "Uvicorn on port 8000. And because it's FastAPI, we get interactive Swagger docs for free at slash docs — which doubles as the API reference for Postman." | Wait for `Application startup complete`, then switch to the browser |

---

## Segment 4 — API surface at /docs (2:10 – 2:50)

| Time | Say | Show |
|---|---|---|
| 2:10 | "Six endpoints. POST /session creates a conversation. POST /chat is the streaming turn. POST /feedback records thumbs up or down. GET /logs returns the full transcript for a session. GET /profile is the mock customer profile bonus, and /health is the liveness check." | `localhost:8000/docs`, scroll the endpoint list once, slowly |
| 2:28 | "Health first." | Expand `GET /health` → Try it out → Execute. Show `{"status":"ok"}` |
| 2:34 | "And the mock profile — user `ayush` comes back as a NovaCart Plus member in Pune with last order NC-10234. Keep that order id in mind, it shows up again in a minute." | Expand `GET /profile/{user_id}`, enter `ayush`, Execute, show the JSON |

---

## Segment 5 — The conversation (2:50 – 5:10)

This is the core of the video. **Type each message exactly as written.** Before the first
message, type `ayush` into the "Demo user id" box in the header.

| Time | Say | Show — type this |
|---|---|---|
| 2:50 | "I'll put a demo user id in the header so we get personalised answers, and start the way a customer would." | Set user id to `ayush`, then send: **`hi`** |
| 2:56 | "It greets back by name — that's the mock profile — and onboards the customer by listing what it can actually help with. That greeting is a prompt rule, not hardcoded text." | Bot reply |
| 3:05 | "Order tracking." | Send: **`where is my order?`** |
| 3:12 | "Grounded answer straight out of the knowledge base, and it references order NC-10234 — the profile from that API call we just made." | Bot reply streaming in |
| 3:22 | "Now the interesting part. This next message is meaningless on its own." | Send: **`i am not able to view that option`** |
| 3:30 | "On its own that scores 0.22 against the knowledge base — well under the 0.30 threshold — and would be written off as out of scope. So the retriever retries it with the previous question attached, which lifts it to 0.56 and pulls the right order-tracking chunks. That's context retention inside retrieval, not just inside the prompt." | Bot reply |
| 3:45 | "Multi-turn follow-up, with a pronoun that only makes sense in context." | Send: **`and what if I want to return it instead?`** |
| 3:53 | "It knows what 'it' is, and switches to the returns and refunds policy." | Bot reply |
| 4:00 | "And it keeps the whole session, not a rolling window of the last few turns." | Send: **`what did I ask you first?`** |
| 4:07 | "Correct. The entire transcript is replayed each turn, limited by a character budget rather than a turn counter." | Bot reply |
| 4:12 | "Out of scope — this is where a chatbot normally hallucinates." | Send: **`who won the 2019 cricket world cup?`** |
| 4:19 | "It doesn't guess. The model returns an ESCALATE sentinel, the server catches it — buffered, so the word never flashes on screen mid-stream — and the bot says plainly that it's not in NovaCart's information, then offers a human." | Bot reply |
| 4:28 | "Frustration detection." | Send: **`this is ridiculous, I've been waiting two weeks and nobody helps me`** |
| 4:34 | "VADER scores that at minus 0.68, past the threshold, so the answer comes with an offer to bring in a person. Stock VADER actually scored this message *positive*, because 'helps' is a positive word — the lexicon is tuned so complaints register and routine questions about damaged items don't." | Bot reply with the human offer line |
| 4:47 | "And when the customer asks outright:" | Send: **`connect me to a human`** |
| 4:52 | "Hard escalation. That's a regex, deliberately not left to the model, so a direct request is always honoured. It quotes the message back so the customer doesn't repeat themselves — and the reply carries the 'Handed to agent' badge." | Bot handoff reply + badge |
| 5:02 | "Last thing: feedback. Thumbs down on the answer it couldn't give, with a comment." | Scroll up, click 👎 on the cricket reply, comment `wanted a real answer` |

> Runs long? Cut turn 4 (`and what if I want to return it instead?`) first — turn 3 already
> proves multi-turn context. Cut turn 5 (`what did I ask you first?`) second.

---

## Segment 6 — Logging (5:10 – 5:30)

| Time | Say | Show |
|---|---|---|
| 5:12 | "Every one of those turns was logged. Here's the transcript for that session." | Copy the session id from the header badge → `/docs` → `GET /logs` → paste → Execute |
| 5:20 | "Role, content, timestamp, the detected intent, the sentiment score, the escalation flag, and the source chunks that grounded each answer — one row per message, user and assistant." | Scroll the JSON response, pause on the escalated row and on a sentiment value |

---

## Segment 7 — Feedback loop (5:30 – 5:45)

| Time | Say | Show |
|---|---|---|
| 5:32 | "The thumbs-down isn't just stored, it feeds a review queue — that's the feedback-loop bonus." | Terminal 2: `python scripts/export_review_queue.py` |
| 5:38 | "Every disliked answer is exported with its question, intent, comment and timestamp, ready for prompt refinement or a new knowledge-base entry." | `cat data/review_queue.json` — show the entry just created |

---

## Segment 8 — Tests (5:45 – 6:00)

| Time | Say | Show |
|---|---|---|
| 5:47 | "28 tests cover the behaviour that matters." | Terminal 2: `python -m pytest tests/ -v` |
| 5:52 | "The escalation policy — out of scope offers a human instead of forcing a handoff, an explicit request escalates, frustration offers but doesn't force. Retrieval finds the right chunk for a known query and falls back for an unknown one. Sentiment separates real complaints from routine questions. And session history keeps short conversations whole while trimming long ones." | *(jump cut past the run)* Scroll the green test names, hold on the pass line |

---

## Segment 9 — Coverage and close (6:00 – 6:30)

| Time | Say | Show |
|---|---|---|
| 6:05 | "Every requirement in the assignment maps to a specific file, and the README has the table: multi-turn conversation, contextual memory, answers only from the FAQ set, escalation, greeting and onboarding, the four query categories, frustration and out-of-scope detection, raw and cleaned documents, embeddings and vector search, keyword lookup, React frontend, grounded responses, timestamped logging, and feedback." | `README.md` coverage table, scroll slowly |
| 6:18 | "All six bonus items are in too — the feedback loop, sentiment detection, the mock customer profile, LangChain for RAG, and multi-user session management." | Keep scrolling to the bonus rows |
| 6:24 | "Postman collection is in the repo covering all six endpoints. That's NovaCart Support — thanks for watching." | `postman/ecommerce-support-bot.postman_collection.json` open in the editor, then cut to the frontend |

---

## Terminal cheat sheet (run order)

```bash
# Terminal 1 — backend
cd backend
source .venv/Scripts/activate          # Windows Git Bash
python scripts/build_index.py          # segment 2
uvicorn app.main:app --reload --port 8000   # segment 3

# Terminal 2 — frontend (start before recording, leave running)
cd frontend
npm run dev

# Terminal 2 — after the chat demo
cd backend
python scripts/export_review_queue.py  # segment 7
cat data/review_queue.json
python -m pytest tests/ -v             # segment 8
```

---

## If something breaks mid-record

| Problem | Fix |
|---|---|
| Reply says "having trouble reaching the support service" | Groq daily quota is gone. Set `GROQ_MODEL=openai/gpt-oss-120b` in `backend/.env`, restart uvicorn, re-record that segment. No code change needed. |
| First message takes ~10s | Cold start — the embedding model loads on first query. Always send one warm-up message before recording. |
| Bot answers the cricket question instead of declining | You're on `gpt-oss-120b`, which grounds less strictly. Switch back to `qwen/qwen3.6-27b` for segment 5. |
| Frustration turn doesn't offer a human | Check `SENTIMENT_NEGATIVE_THRESHOLD` in `app/config.py` is `-0.5` and use the exact wording in the script. |
| `/logs` returns an empty array | Wrong session id — copy it from the header badge in the app, not from an old `/docs` response. |

---

## Requirement → timestamp map

Hand this to the evaluator with the video.

| Assignment requirement | Timestamp | Where in code |
|---|---|---|
| Multi-turn conversation | 3:45 | `chat/session.py` |
| Contextual memory in a session | 3:22, 4:00 | `session.py`, `orchestrator._retrieve_in_context` |
| Answers only from predefined docs (RAG) | 1:05, 3:05 | `rag/`, `llm/prompts.py` |
| Escalation to a human agent | 4:47 | `orchestrator.HUMAN_REQUEST_PATTERN` |
| Greet and onboard | 2:50 | prompt rule in `llm/prompts.py` |
| Order tracking | 3:05 | KB + `intent` from the retrieved chunk |
| Refund / cancellation policy | 3:45 | KB |
| Technical support / pricing | 2:50 (menu in the greeting) | KB categories |
| Frustration detection | 4:28 | `chat/sentiment.py` |
| Out-of-scope detection | 4:12 | retrieval threshold + `ESCALATE` sentinel |
| Raw + cleaned dataset | 1:05 – 1:42 | `data/kb/*.pdf` → `data/kb_chunks.json` |
| Embeddings + vector search | 1:16 | `all-MiniLM-L6-v2` + FAISS |
| Keyword-based lookup | 0:53 (explained) | `rag/keyword_store.py` |
| Web frontend | 2:50 – 5:02 | `frontend/` |
| Deterministic, grounded prompt design | 0:53, 4:19 | temp 0.2 + grounding rules |
| Logging with timestamps | 5:12 | `db/models.py`, `GET /logs` |
| Feedback mechanism | 5:02 | thumbs → `Feedback` table |
| **Bonus** — feedback loop | 5:32 | `scripts/export_review_queue.py` |
| **Bonus** — sentiment detection | 4:28 | VADER, surfaced in the `done` event |
| **Bonus** — customer profile API | 2:34, 3:12 | `profile/mock_profile.py` |
| **Bonus** — LangChain for RAG | 1:16 | loader, splitter, embeddings, FAISS store |
| **Bonus** — multi-user session management | 0:08, 2:50 | `session_id` + optional `user_id` |
| Postman | 6:24 | `postman/` |

---

## Deliberately left out (to hold 6:30)

- File-by-file code tour — `ARCHITECTURE.md` covers it for anyone who wants to read.
- The deviations table (retired Llama model, SSE instead of a single JSON response).
- Groq free-tier quota mechanics.
- The `/health` and `/logs` endpoints having no frontend caller (they exist for
  demonstration and Postman) — mention only if asked.
