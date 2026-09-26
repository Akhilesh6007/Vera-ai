# Vera AI — Merchant Intelligence Assistant

Vera is a context-grounded assistant for merchant engagement. It chooses an appropriate outreach strategy, drafts concise messages from supplied business context, validates facts and calls to action, and manages replies through a replay-safe conversation state machine.

The project includes a browser-only dashboard backed by **localStorage** and an optional FastAPI challenge service. The dashboard runs without a database, API credentials, or a running Python server. All outreach is simulated; this project does not send WhatsApp messages or contact merchants.

**Live demo:** [vera-ai-orpin.vercel.app](https://vera-ai-ak.vercel.app/) · **Repository:** [Akhilesh6007/Vera-ai](https://github.com/Akhilesh6007/Vera-ai)

## What Vera does

- **Routes intent:** detects stop requests, questions, objections, opt-ins, off-topic messages, and automated replies.
- **Protects consent:** gates customer-level outreach on the customer's consent scope; honors STOP and suppresses repeat outreach.
- **Selects a strategy:** routes trigger families to a fitting outreach approach and uses a safe fallback for unknown triggers.
- **Uses relevant context:** selects category, merchant, customer, and trigger data while checking merchant/customer ownership and privacy boundaries.
- **Composes grounded drafts:** generates deterministic messages from available context, with an optional, disabled-by-default LLM provider path.
- **Validates before returning:** checks required output fields, grounding, URLs, category restrictions, and calls to action; invalid provider output falls back to the deterministic composer.
- **Manages conversations:** handles replies, replayed turns, duplicate requests, auto-reply delays, follow-ups, terminal states, and suppression.
- **Runs locally in the browser:** loads the bundled dataset once and persists conversations, context changes, and activity in the browser's localStorage.

## Dataset

The deterministic demo dataset contains **5 categories, 50 merchants, 200 customers, and 100 triggers**. The dashboard loads `local-data.json`; individual JSON context records are also available under `dataset/`. The original challenge materials and seed inputs are retained in `source-archive/`.

`submission.jsonl` and `demo-data.json` are included as local challenge artifacts. Local heuristic results are not an official judge score.

## Run the browser dashboard

Requires Python 3 for its built-in static file server. No package installation or API server is needed for this mode.

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Open <http://127.0.0.1:8765/> and keep the terminal running while you use the dashboard. Stop the server with **Ctrl+C**.

On first launch the dashboard copies `local-data.json` into the browser key `vera-local-workspace-v1`. Later changes persist in that browser profile on that computer. They do not sync to other users or devices. Clearing the site's localStorage removes the saved changes; a refresh seeds the original bundled data again.

## Run the optional challenge API

Requires Python 3.10 or newer.

```bash
python -m venv .venv
```

Activate the environment, then install and start the service:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux / Git Bash
source .venv/bin/activate

python -m pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8080
```

The API keeps context and conversations in process memory; restarting it clears that state. To preload the bundled contexts into the API, set `DEMO_PRELOAD_DATASET=true` before starting it. The browser-only dashboard does not require this API.

Optional LLM providers are disabled by default. Deterministic composition works offline without credentials. See `.env.example` for available configuration names; keep real `.env` files and API keys out of Git.

## Challenge behavior and API

| Route | Purpose |
| --- | --- |
| `GET /v1/healthz` | Health, uptime, and loaded context counts |
| `GET /v1/metadata` | Evaluator-facing team and model metadata |
| `POST /v1/context` | Versioned context ingestion with idempotent equal versions and stale-version rejection |
| `POST /v1/tick` | Process eligible triggers and return grounded draft actions |
| `POST /v1/reply` | Apply intent detection and conversation state transitions to an inbound message |
| `POST /v1/compose` | Preview a draft, strategy, and validation result |
| `GET /v1/dashboard` | Dashboard data, counts, conversation history, and local metrics |
| `GET /v1/evaluation` | Included local submission cases and validation summary |

The API also provides context detail, conversation listing, and system-status routes. Interactive API documentation is available at <http://127.0.0.1:8080/docs> while the API is running.

Example context ingestion:

```bash
curl -X POST http://127.0.0.1:8080/v1/context \
  -H 'Content-Type: application/json' \
  -d '{"scope":"category","context_id":"dentists","version":1,"payload":{"slug":"dentists"}}'
```

## Run the tests and local evaluation

```bash
python -m unittest discover -s tests -v
python generate_submission.py
python evaluate.py
```

The tests cover intent and auto-reply detection, conversation transitions and replay behavior, strategy selection, grounding validation, context privacy and versioning, consent gates, suppression, and service routes. `generate_submission.py` regenerates local rows only when the canonical pair manifest is present. `evaluate.py` labels its output as local heuristic evaluation; it does not call the official judge or an LLM.

## Project structure

```text
app.js                    Browser dashboard and localStorage adapter
app.py                    Optional FastAPI service
bot.py, composer.py       Deterministic composer and optional provider path
intent.py                 Intent and automated-reply detection
conversation_engine.py    Conversation state transitions
conversation_store.py     Replay, suppression, and conversation state
context_store.py          Scoped, versioned context storage
context_builder.py        Privacy-aware context selection
router.py                 Trigger strategy routing
validator.py              Schema, grounding, and policy checks
dataset/                  Expanded challenge contexts
local-data.json           Dataset bundle for browser mode
tests/                    Engine and API service tests
source-archive/           Challenge brief, seed inputs, and references
```

## Deploy

The browser dashboard is a static site and is configured for Vercel through `vercel.json`. The optional Python challenge API is not part of this static deployment. GitHub Pages can also host the browser files from the repository root. In both cases, browser changes remain local to each visitor's browser.

## Limitations

- Browser localStorage is per-browser storage, not shared persistence or a database.
- The optional API uses process memory and is intended for the challenge/demo, not horizontally scaled production state.
- Messages are simulated drafts. No external messaging provider is connected.
- Local metrics and evaluation output are for inspection and are not official judge results.
