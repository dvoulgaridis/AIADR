# AIADR Backend

Local FastAPI backend for AIADR – AI-Assisted Data Review.

## Responsibilities

- Serve API endpoints under `/api/v1/`
- Store review state in SQLite and session files under the configured data directory
- Validate all shared schemas via Pydantic
- Prepare media for model input
- Prepare audio via user-installed FFmpeg when available
- Load and lock a content-hashed instruction-set snapshot when analysis first starts
- Route the locked source-kind prompt to the selected model
- Dispatch provider-neutral inference requests through the configured
  OpenAI-compatible, Anthropic Messages, or Google Gen AI adapter
- Extract model output through `app.findings.extraction`
- Anchor findings through `app.findings.anchoring`
- Resolve classifications and policy effects through `app.policies.mapper`
- Create editable hydrated layers with separate model and reviewer provenance
- Render redacted outputs deterministically
- Persist content-minimized audit events and mode-aware model diagnostics
- Write privacy-minimized export bundles with local shared-secret integrity evidence
- Emit analysis progress events via SSE

## Running

Run the development backend from the repository root:

```bash
uv run python main.py dev
```

The development frontend runs separately with Vite on port 5173; see the root
`README.md` for the complete development workflow.

`run` mode stores and exposes only typed model-call summaries. `dev` mode also
stores raw textual request, response, and provider-error diagnostics for local
debugging. Provider adapters remain transport-only; inference owns these records.
Audit payloads remain content-minimized in both modes.

## API

All endpoints are versioned under `/api/v1/`.
