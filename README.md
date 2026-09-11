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
OPENAI_MODEL=gpt-5.2
```

Optional LangSmith tracing (nested agent + LLM spans in [LangSmith](https://smith.langchain.com/)):

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=ledgerline
# Required for EU workspaces (https://eu.smith.langchain.com):
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

If `LANGSMITH_API_KEY` is set and `LANGSMITH_TRACING` is omitted, tracing is enabled and traces go to project `ledgerline`. Set `LANGSMITH_TRACING=false` to disable.

The OpenAI client is wrapped with `langsmith.wrappers.wrap_openai`. Nested `@traceable` spans cover the orchestrator (`run_ledgerline`), triage, planner, adjudicator, tools, and LLM helpers. Short scripts set `LANGCHAIN_CALLBACKS_BACKGROUND=false` and call `flush_langsmith()` so runs finish uploading before exit.

A `403 Forbidden` on `api.smith.langchain.com` usually means an EU key was sent to the US endpoint — set `LANGSMITH_ENDPOINT` as above.

Optional Galileo tracing (nested agent / workflow / tool / LLM spans in [Galileo](https://app.galileo.ai/)):

```bash
GALILEO_API_KEY=your-galileo-api-key
GALILEO_PROJECT=demo app
GALILEO_LOG_STREAM=demo app
```

The OpenAI client is wrapped with Galileo's SDK so every `chat.completions` call is an LLM span. Agent entry points and adjudicator tools are also `@log`-decorated. Set `GALILEO_LOGGING_DISABLED=true` to turn it off. Custom Galileo deployments need `GALILEO_CONSOLE_URL`.

Optional Langfuse tracing (nested `@observe` spans + OpenAI generations in [Langfuse](https://cloud.langfuse.com/)):

```bash
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
```

One scan is one Langfuse trace, with both agents nested under the orchestrator:

```
scan-inbox            (agent)
├── triage-invoices   (agent)
│   └── analyze-email (span)          one per email
│       └── classify-invoice (generation)
└── plan-payments     (agent)
    └── rank-invoices (generation)
```

Set `LANGFUSE_TRACING_ENABLED=false` to turn it off. US cloud is `https://us.cloud.langfuse.com`. Emails and card-like numbers are masked before they leave the process.

Optional Braintrust tracing (`init_logger` + `auto_instrument` + `@traced` spans in [Braintrust](https://www.braintrust.dev/)):

```bash
BRAINTRUST_API_KEY=sk-...
BRAINTRUST_API_URL=https://api-eu.braintrust.dev
BRAINTRUST_PROJECT=My Project
BRAINTRUST_PROJECT_ID=b9a5698f-8159-4af9-bb06-844496357d5f
```

Omit `BRAINTRUST_API_URL` for the US API (`https://api.braintrust.dev`). Set `BRAINTRUST_TRACING=false` to turn it off.

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

## Ledgerline Adjudicator

A third agent decides whether a submitted **expense claim** is reimbursable. Unlike
triage, it is multi-step: the model must call tools to retrieve the policy clause,
an FX rate, and submitter history, then `post_decision` before returning JSON
(`approve` / `partial` / `reject` / `escalate`).

Tools are backed by a deterministic in-repo fixture store (`adjudicator_fixtures.py`).
The same arguments always return the same output so eval replay is stable.

Trace-producing runs pin **gpt-5.6** via `ADJUDICATOR_MODEL` (default `gpt-5.6`).
This is independent of `OPENAI_MODEL`, which remains the triage/planner default
(`gpt-5.2`).

```bash
python -m scripts.run_adjudicator_100 --check-tools   # fixture determinism, no LLM
python -m scripts.run_adjudicator_100 --limit 5
python -m scripts.run_adjudicator_100                 # 100 claims + sidecar JSONL
# or: make run-adjudicator-100
```

The sidecar is written to `artifacts/adjudicator-100.jsonl` (claim input +
constructed ground truth + model output).

A disjoint eval corpus (`CLM-E-*`, session `adjudicator-eval-100-YYYYMMDD`) is
run separately so train and eval never share claim ids or traces:

```bash
python -m scripts.run_adjudicator_eval_100 --limit 5
python -m scripts.run_adjudicator_eval_100
# or: make run-adjudicator-eval-100
```

The eval sidecar is `artifacts/adjudicator-eval-100.jsonl`.

HTTP: `POST /api/adjudicate` with an `ExpenseClaim` JSON body.

## Scripts

```bash
verify-agent      # mocked LLM unit check (no network)
run-both-agents   # triage + payment planner over the demo corpus (--limit N, --json)
run-20-emails     # handcrafted demo corpus through analyze_email
run-100-emails    # generated corpus (DEMO_EMAIL_COUNT or 100)
run-250-emails    # generated corpus (DEMO_EMAIL_COUNT or 250)
run-themes        # themes stress harness (prefers Ollama when set)
run-eval-50        # gold eval A (50 scenarios)
run-eval-50b       # gold eval B (50 scenarios)
run-adjudicator-100       # expense adjudicator train 100 (ADJUDICATOR_MODEL)
run-adjudicator-eval-100  # disjoint eval 100 (same mix, new claim ids)
dev                # uvicorn with reload on :8000
```

Or via module:

```bash
python -m scripts.verify_agent
python -m scripts.run_both_agents --limit 6
python -m scripts.run_adjudicator_100 --limit 5
python -m scripts.run_adjudicator_eval_100 --limit 5
```

## API

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/api/auth/google` | 302 to Google OAuth |
| GET | `/api/auth/callback` | Store tokens, redirect `/?connected=1` |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/status` | Auth + LLM status JSON |
| POST | `/api/scan` | `{mode?: "gmail"\|"demo"}` → scan result |
| POST | `/api/adjudicate` | Expense claim JSON → adjudication |
