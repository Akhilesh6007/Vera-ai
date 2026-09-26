# Vera AI · magicpin Merchant AI Challenge

Vera is a context-grounded merchant assistant with a browser-only local mode and an optional challenge HTTP API. All outreach in this project is simulated; no WhatsApp or merchant messaging API is called.

## Dataset

The supplied archive is preserved under `source-archive/`. Its deterministic seed expander produced `dataset/` with **5 categories, 50 merchants, 200 customers, 100 triggers, and 30 canonical pairs**. `local-data.json` bundles these contexts for browser-only mode, and `submission.jsonl` has one JSON object for each canonical pair.

## Architecture

- `context_store.py`: thread-safe scope/id/version store. Equal versions are idempotent, higher versions replace atomically, and stale versions return 409.
- `conversation_store.py`, `conversation_engine.py`: process-lifetime conversation history, replay-safe turn idempotency, STOP suppression, the send/wait/end state machine, and timed auto-reply backoff/re-engagement.
- `router.py`, `context_builder.py`, `intent.py`, `language.py`: strategy routing, privacy-filtered context selection, intent/auto-reply detection, and per-turn language detection.
- `bot.py` + `composer.py`: deterministic context composer plus an opt-in LLM path. `validator.py` checks output schema, grounding tokens, URLs, and category taboos; invalid LLM drafts fall back to the deterministic composer after at most two repairs.
- `app.py`: required `/v1/context`, `/v1/tick`, `/v1/reply`, `/v1/healthz`, `/v1/metadata` endpoints plus read-only/demo routes used by the dashboard.
- `index.html`, `styles.css`, `app.js`, `local-data.json`: dashboard and deterministic browser-side data adapter. On first open, the bundled contexts are copied into `localStorage`; simulated conversations and context updates persist there without a database or API process.

LLM use is off by default. The optional `OpenAI` chat-completions provider and local `Ollama` provider use temperature 0, short timeouts, and the versioned `composer_v1` prompt. The deterministic fallback works without credentials and is the default for judge compatibility. Context is not sent to any external provider unless the operator explicitly enables an LLM and configures it.

## Start the browser-only live preview

From the project folder in Git Bash or PowerShell:

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765`. This mode does not need the API server or a database. First launch seeds the browser key `vera-local-workspace-v1` from `local-data.json`; conversations, context updates, suppression, and local activity telemetry are saved after each change. The data belongs to that browser profile on that computer. Clearing this site's local storage removes the saved changes; refreshing then seeds it again from the bundled data.

The challenge API remains available as an optional mode for simulator work. Start it separately with `python -m uvicorn app:app --host 127.0.0.1 --port 8080`; use `DEMO_PRELOAD_DATASET=true` when starting it if you want the API itself to preload the dataset.

## API and local checks

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python generate_submission.py
python evaluate.py
```

The engine suite includes hidden-context/privacy checks, injected-context adaptation, customer-consent gates, strategy/validator cases, and multi-turn replay scenarios. It runs offline and does not call the optional LLM provider.

The service exposes:

| Method | Route | Purpose |
|---|---|---|
| GET | `/v1/healthz` | Uptime and actual loaded-context counts |
| GET | `/v1/metadata` | Safe environment-based team/model metadata |
| POST | `/v1/context` | Versioned context ingestion |
| POST | `/v1/tick` | Trigger resolution, consent, expiry, suppression and proactive action |
| POST | `/v1/reply` | Stateful `send` / `wait` / `end` conversation turn |

Read-only demo routes include `/v1/dashboard`, `/v1/context/{scope}/{id}`, `/v1/conversations`, `/v1/evaluation`, `/v1/compose`, and `/v1/system`. `/v1/compose` is a preview only; `/v1/tick` creates an in-memory conversation.

## Judge simulator

The provided simulator uses its own external LLM key to score messages. With the bot running on port 8080, its network/integration scenarios can be run without a judge key:

```powershell
@'
import sys
sys.path.insert(0, 'source-archive')
import judge_simulator as sim
class NoScoreJudge:
    def name(self): return 'local integration only'
    def complete(self, prompt, system=None): raise RuntimeError('Scoring key not configured')
ok = sim.JudgeSimulator(NoScoreJudge()).run('all')
raise SystemExit(0 if ok else 1)
'@ | python -
```

This exercises warmup, context pushes, tick, canned auto-reply, explicit intent, and hostile-stop flows without claiming official scores. Configure a judge provider/key in the simulator itself to run AI scoring; keep all keys out of the project.

## Evaluation and limitations

`evaluate.py` reports **local heuristic** structural/routing results, not official judge scores. Official quality scoring needs the simulator's external judge LLM credential. The challenge dataset is synthetic. Process memory stores state by design, which survives all requests during a run but resets on server restart. Demo KPI cards use dataset counts and local in-process metrics; they do not suggest real production engagement rates.
