# CentrAlign Demo Video Script

## Target length

Approximately 3–4 minutes.

## 1. Introduction — 20 seconds

> Hi, I’m Nirwan. I built CentrAlign, a narrow autonomous AI worker for invoice processing.
>
> The system takes a natural-language goal, discovers an invoice, extracts its data, reconciles it against a purchase order, operates a simulated ERP through a browser, requests approval for high-value invoices, and independently verifies the result.
>
> I learned about this opportunity today and had less than two hours to work on this prototype, so I focused on making one workflow genuinely functional.

## 2. Start the system — 20 seconds

Open two terminals.

Terminal 1:

```bash
cd /Users/nirwan-teji/Developer/CentrAlign
source .venv/bin/activate
python -m sandbox.erp_app
```

Terminal 2:

```bash
cd /Users/nirwan-teji/Developer/CentrAlign
source .venv/bin/activate
python run.py
```

Open `http://localhost:8000`.

> The first process is the simulated ERP. The second process is the CentrAlign agent console.

## 3. Submit a high-level goal — 20 seconds

Enter this into the goal field:

```text
Find the latest invoice, reconcile it against its purchase order, and submit it to the ERP.
```

> I’m giving the worker a business outcome rather than specifying every individual action.

Click **Start run**.

## 4. Show autonomous execution — 60 seconds

While the trace is running, narrate:

> The worker first discovers the latest invoice from the local repository.
>
> It extracts structured information including the vendor, invoice number, dates, purchase order, line items, and total amount.
>
> It then looks up the matching purchase order and uses a deterministic reconciliation tool to compare the invoice total against the PO total.
>
> After reconciliation, it starts a Playwright browser session, logs into the ERP, opens the invoice form, and fills the form using the facts discovered earlier.

Point to trace events such as:

```text
find_latest_invoice
parse_invoice
lookup_purchase_order
reconcile
navigate
type_text
submit_invoice
```

## 5. Demonstrate human approval — 30 seconds

When the approval panel appears:

> This invoice is above the configured five-thousand-dollar approval threshold, so the worker pauses instead of submitting automatically.
>
> The approval request includes the reason and relevant invoice data. This is the human-in-the-loop safety boundary.

Click **Approve**.

> After approval, execution resumes from the paused step.

## 6. Show verification and evidence — 40 seconds

When the run completes:

> The invoice has now been submitted through the browser.
>
> The worker does not trust the form response alone. It independently queries the ERP API to confirm that the record was actually persisted.
>
> It also captures before-and-after screenshots and generates an audit evidence package containing the goal, execution observations, verification result, and record ID.

Show the generated files under:

```text
data/evidence/<run-id>/
```

Point out:

```text
evidence_package.json
audit_summary.md
```

## 7. Optional failure-recovery demonstration — 40 seconds

Before starting another run, enable a one-time ERP validation failure:

```bash
curl -X POST "http://localhost:8001/chaos/set?validation_error_mode=true"
```

Run the same goal again.

When the error appears:

> I’ve enabled a one-time validation failure in the ERP sandbox.
>
> The worker observes the validation error, classifies it as recoverable, retries the submission, and continues without manual intervention.

Reset the sandbox afterward:

```bash
curl -X POST http://localhost:8001/chaos/reset
```

## 8. Architecture closing — 30 seconds

Show the GitHub repository and say:

> The architecture follows the loop Goal → Plan → Execute → Observe → Adapt → Verify → Complete.
>
> The main components are a typed agent runtime, planner, tool registry, working memory, browser automation layer, human-approval policy gate, independent verifier, and evidence packager.
>
> The system is intentionally narrow and uses a local sandbox. With more time, I would add durable task queues, stronger document understanding, broader browser workflows, production authentication, and persistent storage.

> I wasn’t able to spend as much time on this prototype as I would have liked, but I hope it demonstrates the direction and meets the expectations for a working proof of concept. If shortlisted, I would make the product more solid by adding stronger test coverage, more reliable recovery strategies, persistent execution state, better security and permission controls, richer document extraction, and a more polished user experience. I would be excited to use the technical discussion to present and improve a more complete version.

## Final line

> Although this is a prototype built under a very limited time window, it performs real work in a browser, handles a failure, pauses for approval, verifies the result, and produces evidence rather than only describing what should happen.
