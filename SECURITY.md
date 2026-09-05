# Security Policy

## Supported versions

Security fixes are applied to the latest commit on the default branch. This
repository is a portfolio prototype, not certified building-code software.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private IFC
models, or regulation documents. Use the repository's private GitHub Security
Advisory reporting channel when it is available. Otherwise, contact the
repository owner privately and include the affected revision, impact, and a
minimal reproduction that contains no confidential project data.

## Deployment expectations

- Keep the API on loopback unless authentication and a production reverse proxy
  are configured.
- Generate a unique `MINI_AEC_SERVICE_API_KEY` of at least 16 characters and
  rotate it if it is exposed. Never commit `.env` files.
- Terminate TLS, rate-limit requests, set connection timeouts, and cap request
  sizes at the reverse proxy for any shared deployment.
- Treat IFC files, PDFs, retrieval text, model output, and model tool calls as
  untrusted input. Process confidential models only in an approved environment.
- Treat traces, reports, and telemetry as potentially sensitive project data;
  restrict their storage, access, retention, and export destinations.
- Keep lock files current and review Dependabot, dependency-audit, static-scan,
  and secret-scan results before release.
- Treat every compliance result as review evidence, not legal approval. A
  qualified professional must verify source editions, rule applicability,
  measurements, and final decisions.

## Implemented controls

The service uses fixed tool dispatch, strict request and data schemas, bounded
agent steps and payloads, constant-time API-key comparison, non-root read-only
container settings, deterministic rule evaluation, source provenance, atomic
artifact writes, dependency and static-security scans, and an opt-in telemetry
path. See `docs/architecture.md` for trust boundaries and residual limitations.
