# Architecture Decision Record (ADR) — CentrAlign AI Employee Prototype

This document tracks all key technical, architectural, and design decisions made throughout the engineering lifecycle of this project.

---

## ADR Template
Every architectural or design decision made by the implementing agent must be recorded in this format:

```markdown
### ADR-[Number]: [Short Title]
- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded | Deprecated
- **Context & Problem Statement:** What problem were we solving? What constraints existed?
- **Decision:** What was chosen and how is it implemented?
- **Alternatives Considered:** What other options were evaluated?
- **Tradeoffs & Consequences:** Why is this superior? What are the limitations or operational impacts?
```

---

### ADR-001: Core LLM Selection — OpenAI GPT-OSS 120B on Groq
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  CentrAlign's autonomous AI worker requires fast multi-turn reasoning, reliable tool selection, and JSON structured outputs without incurring significant API costs or facing restrictive rate limits.
- **Decision:**
  Select `openai/gpt-oss-120b` served via Groq Cloud API as the primary reasoning and acting engine, with configurable fallbacks to `llama-3.3-70b-versatile`.
- **Alternatives Considered:**
  1. *Proprietary Closed Models (GPT-4o, Claude 3.5 Sonnet):* Powerful but high cost per token and subject to rate limits during tight agentic test loops.
  2. *Local 8B models (e.g. Ollama Llama 3 8B):* Zero external API cost, but high inference latency on consumer CPUs/GPUs and less reliable tool-calling and self-correction.
- **Tradeoffs & Consequences:**
  - *Pros:* Groq LPUs deliver ~500 tokens/second, enabling near-instantaneous agent decision loops. Free/ultra-low cost tier. 131k context window allows multi-step history and DOM snapshots.
  - *Cons:* Relies on network connection to Groq API. Fallback models must be supported if Groq experiences temporary downtime.

---

### ADR-002: Local Vector Embeddings & In-Memory / SQLite Vector Store
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  The agent needs episodic memory to store company policies, past task execution traces, and schema guidelines without adding paid API dependencies or network latency.
- **Decision:**
  Use local open-source embeddings (`BAAI/bge-small-en-v1.5` or `sentence-transformers/all-MiniLM-L6-v2` via FastEmbed / Sentence-Transformers) paired with local ChromaDB / SQLite.
- **Alternatives Considered:**
  1. *OpenAI text-embedding-3-small:* Incurs API costs, network overhead, and API key management.
- **Tradeoffs & Consequences:**
  - *Pros:* 100% free, deterministic, ultra-fast CPU inference, zero third-party data transmission.
  - *Cons:* Model weights (~120MB) downloaded once during setup.

---

### ADR-003: Browser Automation Engine — Playwright with Accessibility & DOM Distillation
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  An AI employee must interact with enterprise web applications. Passing raw HTML to the LLM consumes huge token budgets and confuses the model with styling scripts.
- **Decision:**
  Use Python Async Playwright with a custom DOM distillation parser that extracts an interactive accessibility map (IDs, roles, text labels, and input states) and captures visual screenshots for verification evidence.
- **Alternatives Considered:**
  1. *Selenium:* Slower, heavier setup, less modern async support.
  2. *Pure HTTP requests (requests/httpx):* Cannot handle modern client-side JavaScript applications, form states, dynamic modals, or visual evidence capture.
- **Tradeoffs & Consequences:**
  - *Pros:* Modern, fast, supports full browser context, robust selector waiting, headless and headed modes, native screenshotting.
  - *Cons:* Requires Chromium browser installation (`playwright install chromium`).

---

### ADR-004: Self-Contained Sandbox Enterprise Environment
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  CentrAlign's evaluation guidelines strictly prohibit using real company credentials or unauthorized access to third-party production systems. The prototype must demonstrate genuine autonomy on a realistic workflow.
- **Decision:**
  Build a dedicated internal mock ERP web application (FastAPI + HTML5) simulating an enterprise accounting portal with real authentication, forms, pagination, and configurable chaos triggers (validation errors, network blips) to test the agent's failure recovery.
- **Alternatives Considered:**
  1. *Mocking tools via simple Python stubs:* Does not test actual browser automation or visual verification.
  2. *Testing against public websites (e.g. Amazon, GitHub):* Flaky, risks CAPTCHAs, bot blocks, and rate limits.
- **Tradeoffs & Consequences:**
  - *Pros:* 100% reliable, zero risk of credentials exposure, deterministic test benchmarks, and reproducible live demos.
- *Cons:* Requires building and maintaining the mock ERP application within the codebase.

### ADR-005: Deterministic Agent Execution Loop with Bounded Recovery
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  A free-form LLM loop can repeat actions indefinitely, lose completed work after an error, or report success without independently checking the outcome.
- **Decision:**
  Implement Phase 4 as an explicit asynchronous state-machine loop. Plans contain typed action steps; every tool result becomes an `Observation` and updates working memory. Recovery is bounded by per-step retry counts and a global step budget, while `Verifier` checks plan completion and evidence after execution. Human approval is represented by a typed `HITLRequest` and is required for explicitly flagged steps or amounts above the configured threshold.
- **Alternatives Considered:**
  1. *Pure LLM orchestration:* More flexible, but difficult to make safe, reproducible, and testable.
  2. *Unstructured exception handling:* Simpler initially, but loses audit context and recovery decisions.
- **Tradeoffs & Consequences:**
  - *Pros:* Reproducible tests, bounded failure behavior, preserved facts, auditable evidence, and injectable fakes for local testing.
  - *Cons:* Deterministic recovery covers known transient/validation failures; novel failures require a future planner-generated replan.

### ADR-006: Policy-Backed HITL and Persistent Audit Memory
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  Financial automation needs explicit safety boundaries and continuity across runs without silently approving risky actions.
- **Decision:**
  Keep working memory in each run, use the existing ChromaDB-backed episodic memory for durable retrieval, and put approval rules in a small replaceable `CompanyPolicy` component. High-value amounts, unknown vendors, explicit plan flags, and repeated failures can produce a typed `HITLRequest`.
- **Alternatives Considered:**
  1. *Inline threshold checks only:* Easy to start, but difficult to extend and audit.
  2. *External policy service:* More scalable, but unnecessary for a self-contained prototype.
- **Tradeoffs & Consequences:**
  Policy decisions are deterministic and testable locally; production deployments can replace `CompanyPolicy` with a signed policy service.

### ADR-007: Independent Verification and Evidence Packs
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  A successful browser action is not proof that an ERP record was persisted.
- **Decision:**
  Verification is a separate runtime component. Workflows can require an explicit successful `query_erp_db` confirmation or inject an independent checker. Every run serializes the goal, timeline, observations, screenshots, verification verdict, and failure reason into JSON and Markdown audit artifacts.
- **Alternatives Considered:**
  Trusting the final form response was rejected because it permits false-positive completion.
- **Tradeoffs & Consequences:**
  The extra check costs one tool call but supplies defensible evidence and makes failed persistence visible.

### ADR-008: SSE Observation Console and Rich CLI
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  Reviewers need to observe long-running work and resolve approvals without coupling the runtime to a browser UI.
- **Decision:**
  Use FastAPI with an in-process event broker and Server-Sent Events for one-way trace updates; expose approval and run APIs, plus a static dark-mode dashboard. Provide a Rich/Typer CLI over the same engine for headless demonstrations.
- **Alternatives Considered:**
  WebSockets were not selected because the primary stream is server-to-client; approval is a separate HTTP command.
- **Tradeoffs & Consequences:**
  SSE is simple and browser-native for this prototype. A multi-worker deployment will need an external broker and durable run store.

### ADR-009: Deterministic Evaluation Scenarios
- **Date:** 2026-10-18
- **Status:** Accepted
- **Context & Problem Statement:**
  End-to-end claims need repeatable tests independent of Groq availability and third-party systems.
- **Decision:**
  Evaluation tests use the local ERP ASGI app, injectable tools, deterministic offline planning, chaos toggles, and temporary evidence directories. Groq and Chromium remain optional integrations for live demonstrations.
- **Alternatives Considered:**
  Live production systems and public websites were rejected as unsafe and flaky.
- **Tradeoffs & Consequences:**
  The benchmarks are reproducible and safe, while headed browser/video demos still require local Playwright installation.

### ADR-010: Fact-Carrying Invoice Workflow and Mandatory Mutation Verification
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context & Problem Statement:**
  The prototype needed to demonstrate actual autonomous work rather than only isolated tools and fake-agent tests.
- **Decision:**
  Add invoice discovery/parsing, PO lookup, runtime fact interpolation, browser-backed ERP submission, mandatory database confirmation for mutation plans, and before/after screenshots. Evaluate HITL thresholds after facts are resolved.
- **Alternatives Considered:**
  Keep the offline plan file-only, rely only on LLM-generated browser plans, or submit directly over HTTP.
- **Tradeoffs & Consequences:**
  The local demo is reproducible and genuinely exercises Playwright, while the workflow remains limited to the sandbox ERP and supported invoice formats.

### ADR-011: Browser-Compatible Human Approval Console
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context & Problem Statement:**
  A backend approval endpoint is insufficient if a reviewer cannot act from the live console.
- **Decision:**
  Add an SSE-triggered approval panel with approve, reject, and guidance actions, plus safe evidence artifact endpoints for completed runs.
- **Alternatives Considered:**
  Manual API calls or terminal-only approval.
- **Tradeoffs & Consequences:**
  The in-process console is suitable for the prototype; production deployments would need durable run state and authenticated artifact access.

### ADR-012: Render Two-Service Blueprint
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context & Problem Statement:**
  The browser worker and sandbox ERP are separate local processes and must remain independently reachable after deployment.
- **Decision:**
  Define `centralign-agent` and `centralign-erp` as Render Python web services. The agent receives the ERP private host/port through a Blueprint `fromService` reference, binds to Render's `$PORT`, and installs Chromium during its build.
- **Alternatives Considered:**
  Combine both ASGI apps into one process or expose the ERP publicly and hard-code its URL.
- **Tradeoffs & Consequences:**
  Two services preserve the local architecture and avoid exposing the ERP, but Render free-tier storage is ephemeral and browser dependencies make agent builds heavier.
