# Ledgerline — LLM Invoice Email Agent (Python)

Local FastAPI app that connects to Gmail with **read-only** access and uses an **LLM** to:

- triage which emails are invoices
- extract how much each invoice is for
- extract when payment is due

There is no heuristic fallback — scanning requires a model API key (or local Ollama).

Package name: `invoice-agent`. Brand: **Ledgerline**.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env.local
```

Add at least one LLM config to `.env.local`:

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Or for a fully local model:

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2
```

Then:

```bash
dev
# or: uvicorn invoice_agent.app:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

Use **Run demo scan** to test the LLM on sample emails, or connect Gmail for real inbox data.

## Connect Gmail (read-only)

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Gmail API**.
3. Configure the OAuth consent screen (External is fine for personal use; add your Google account as a test user).
4. Create OAuth credentials → **Web application**.
5. Add authorized redirect URI:
   `http://localhost:8000/api/auth/callback`
6. Put the client ID/secret into `.env.local` (see `.env.example`).
7. Restart the server, then click **Connect Gmail (read-only)**.

Requested scopes:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/userinfo.email`

Tokens are stored in an encrypted httpOnly session cookie on your machine.

## How the agents work

Two agents run in sequence on every scan.

**1. Invoice triage** (`invoice_agent.agent.triage`)

1. Loads recent inbox emails (+ PDF attachment text when present), or the demo corpus
2. Sends each email to the LLM for triage + extraction (one chat completion, `temperature=0`, JSON object)
3. Keeps only messages the model marks as payable invoices
4. Shows vendor, amount, due date, invoice number, and confidence

**2. Payment planner** (`invoice_agent.agent.planner`)

1. Takes the invoices triage extracted and sends them to the LLM in one call
2. Ranks each invoice as `pay_now`, `schedule`, or `hold` with a `payBy` date and a reason
3. Adds portfolio-level risk flags (duplicates, missing fields, large exposure)
4. Totals per currency are summed in Python, never by the model

The planner never fails a scan: if its call or JSON is unusable, it falls back to
deterministic due-date rules and marks the plan `source` as `fallback`.

## Tracing (Langfuse)

Tracing turns on only when both keys are present in `.env.local`; without them the app
runs exactly as before.

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
```

One scan is one trace, with both agents nested under the orchestrator:

```
scan-inbox            (agent)  input: mode + email count, output: invoices + plan
├── triage-invoices   (agent)
│   └── analyze-email (span)        one per email
│       └── classify-invoice (generation)
└── plan-payments     (agent)
    └── rank-invoices (generation)
```

Running a single email through `analyze_email` (the eval scripts) produces a
`triage-email` trace instead, since one email is the whole unit of work there.

These observation names are stable, so per-agent slicing needs no custom tagging:
filter observations by `name=triage-invoices` or `name=plan-payments` for agent-level
latency and error rates, or by `name=classify-invoice` / `name=rank-invoices` for the
cost and token usage of each agent's model calls.

Traces carry the Gmail address as `user_id`, the package version, and
`mode:gmail` / `mode:demo` tags. Email addresses and card-like numbers are masked
before anything leaves the process (`src/invoice_agent/observability.py`). When the
planner falls back to due-date rules, its observation is marked `WARNING` with the
reason as the status message, so failed plans are filterable in the UI.

## Scripts

```bash
verify-agent      # mocked LLM unit check (no network)
run-both-agents   # triage + payment planner over the demo corpus (--limit N, --json)
run-20-emails     # handcrafted demo corpus through analyze_email
run-100-emails    # generated corpus (DEMO_EMAIL_COUNT or 100)
run-250-emails    # generated corpus (DEMO_EMAIL_COUNT or 250)
run-themes        # themes stress harness (prefers Ollama when set)
run-eval-50       # gold eval A (50 scenarios)
run-eval-50b      # gold eval B (50 scenarios)
dev               # uvicorn with reload on :8000
```

Or via module:

```bash
python -m scripts.verify_agent
python -m scripts.run_both_agents --limit 6
```

## API

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/api/auth/google` | 302 to Google OAuth |
| GET | `/api/auth/callback` | Store tokens, redirect `/?connected=1` |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/status` | Auth + LLM status JSON |
| POST | `/api/scan` | `{mode?: "gmail"\|"demo"}` → scan result |
