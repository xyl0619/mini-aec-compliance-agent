# Contributing

## Local setup

Use Python 3.11-3.13 and the committed lock file:

```bash
uv sync --locked --extra dev --extra security
```

Keep real credentials in an ignored `.env` file. Test fixtures must contain
obviously fake values only.

## Required checks

Before opening a change, run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov=mini_aec_agent --cov-fail-under=85
uv run bandit -r src rag evaluation scripts agent.py tools.py main.py -q
```

CI additionally audits the locked runtime dependencies, checks the secret-scan
baseline, validates Compose, and builds the production image.

## Rule and benchmark changes

- Never represent invented thresholds as statutory requirements.
- Every prototype or validated rule needs source metadata, page/clause evidence,
  edition information, and a clear review status.
- Keep deterministic decisions in Python; the model may select tools and explain
  evidence but must not silently replace rule outcomes.
- Add tests for malformed and missing evidence as well as the happy path.
- Report benchmark case counts and scope with every metric. Do not generalize a
  small single-document benchmark into a reliability or legal-accuracy claim.

## Pull requests

Keep changes focused, explain observable behavior and trust-boundary impact, and
include the commands used to verify the change. Do not attach confidential IFC
models, regulation files, traces, or credentials to issues or pull requests.
