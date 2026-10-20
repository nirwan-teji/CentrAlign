# CentrAlign AI

CentrAlign is a local autonomous invoice worker. Given a natural-language goal, it discovers and parses an invoice, looks up its purchase order, reconciles totals, operates a browser against a sandbox ERP, requests approval for high-value submissions, verifies the persisted record independently, and writes an audit pack.

## Architecture

```text
Goal -> Planner -> Typed tools -> Filesystem extraction + PO reconciliation
     -> Playwright ERP execution -> Observe / Working Memory -> Adapt
     -> HITL policy gate -> Independent ERP query + screenshots -> Evidence pack
```

The runtime is in `core/`. Tools are in `tools/`, the safe local enterprise application is in `sandbox/`, and the observation console is in `server/`.

## Setup and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

The Groq key is optional. Start the ERP and agent console in separate terminals:

```bash
python -m sandbox.erp_app
python run.py
```

Open `http://localhost:8000`. The terminal runner is also available:

```bash
python -m cli.main run "Find the latest invoice, reconcile it against its purchase order, and submit it to the ERP"
```

The sandbox demo credentials are `admin` / `admin123`. The worker refuses external browser URLs and only permits localhost navigation.

## What the demo proves

- Newest-invoice discovery by invoice date.
- TXT and CSV parsing; PDF extraction through `pypdf`.
- Structured facts carried between tools through working memory.
- Deterministic purchase-order reconciliation.
- Real Playwright login and HTML-form submission.
- Recovery from an injected ERP validation failure.
- Human approval for amounts above the configured `$5,000` threshold.
- Mandatory ERP database confirmation and visual screenshot evidence.
- JSON and Markdown audit artifacts under `data/evidence/<run-id>/`.

## Tests

Run the hermetic suite offline:

```bash
HF_HUB_OFFLINE=1 pytest -v tests/
```

The real browser test is opt-in and requires the ERP to be running:

```bash
RUN_BROWSER_E2E=1 HF_HUB_OFFLINE=1 pytest -q tests/integration/test_real_browser_workflow.py -s
```

That test exercises the real Playwright path, injects an ERP validation failure, checks recovery, approves the high-value invoice, and verifies the persisted database record and screenshots.

## Submission notes

Assumptions: the prototype operates inside a trusted local sandbox, invoice formats are limited to the included fixtures, and the ERP has a stable HTML form/API. It is not production-ready: browser sessions and run state are in-process, the policy store is local, and desktop applications are not supported.

Models and components: optional Groq `openai/gpt-oss-120b` with a configurable fallback, local Sentence Transformers embeddings, FastAPI, Playwright, Pydantic, ChromaDB, `pypdf`, Typer, and Rich. No production credentials or third-party ERP access are used.

Next steps would be durable queued execution, externalized policy and memory services, richer document/OCR extraction, desktop computer use, multi-worker event storage, and broader evaluation scenarios.

Architecture decisions are recorded in [decisions.md](decisions.md).

## Render deployment

The repository includes `render.yaml`, which defines two Singapore-region web services: `centralign-erp` and `centralign-agent`. In Render, choose **New → Blueprint**, select this repository, and sync the Blueprint. When prompted, provide `GROQ_API_KEY` or leave it blank to use the deterministic local planner. Open the URL for `centralign-agent` after both services are healthy.

The free-tier deployment uses ephemeral local storage for ChromaDB, evidence, screenshots, and the mock ERP database. It is intended for a demonstration, not durable production data.

For manual two-service setup, deploy the ERP first, copy its public `https://...onrender.com` URL, and set that URL as `SANDBOX_ERP_URL` on the agent service.
