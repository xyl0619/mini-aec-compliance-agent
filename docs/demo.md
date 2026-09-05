# Interview Demo

This script demonstrates the engineering boundaries without requiring a live
model key until the final optional step.

## 1. Prove the deterministic IFC path

```bash
uv run python scripts/generate_ifc_report.py \
  --ifc examples/sample_office.ifc \
  --output artifacts/sample-report.json
```

Expected result: three doors are checked against the prototype BFA catalog;
two pass and the 780 mm `Door-01` fails the 800 mm rule. Its finding includes
the IFC GlobalId, explicit `Pset_MiniAEC.OnAccessibleRoute` and
`Pset_MiniAEC.ClearOpeningWidth` evidence, catalog version, clause 38, PDF page
66, source URL, and verification state.

## 2. Show retrieval evaluation

After creating the local regulation index as described in the README:

```bash
uv run python -m evaluation.evaluate_retrieval
```

The committed eight-case bootstrap result records Hit@5 and mean reciprocal
rank. Present it as a small regression benchmark over one document, not as a
general accuracy claim.

## 3. Show the service surface

```powershell
$env:MINI_AEC_IFC_FILE = "examples/sample_office.ifc"
uv run mini-aec-api
```

Open `http://127.0.0.1:8000/docs`, inspect an IFC element by GlobalId, run a
deterministic check, and generate the batch report. Agent run responses expose
steps, token usage, tool/model call counts, and latency; full tool evidence is
available with `include_trace=true`.

To demonstrate the security control, restart with
`MINI_AEC_SERVICE_API_KEY` set. `/v1` requests then require `X-API-Key`, while
`/health` remains usable by deployment probes.

For the Compose demo, set a unique service key first; Compose refuses to start
without it and exposes the container only on `127.0.0.1:8000`.

## 4. Optional live-agent demo

With `TOGETHER_API_KEY` configured:

```bash
uv run mini-aec-agent \
  --ifc examples/sample_office.ifc \
  --question "Which IFC doors fail the accessible-width rule, and what is the source?" \
  --trace
```

Point out the separation: the model chooses the sequence and writes the answer;
Python tools make the decision and return source-bearing evidence.

## Resume-safe evidence

- Built a bounded tool-calling agent with deterministic compliance decisions.
- Added read-only IFC4 ingestion and source-level evidence by GlobalId.
- Implemented page-aware regulation RAG with reproducible index metadata.
- Shipped CLI and FastAPI interfaces, optional API-key auth, Docker, CI across
  Python 3.11-3.13, strict typing/linting, coverage enforcement, and
  OpenTelemetry instrumentation.
- Added dependency, static-code, and secret scanning plus a hardened non-root,
  read-only container build.
- Keep benchmark scope explicit: report the case count together with the metric.
