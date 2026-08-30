## AGENTS.md

### Architecture

Read [docs/architecture.md](docs/architecture.md) before making architectural or
cross-layer changes. Respect the ownership boundaries described there.

Keep API routes thin. Keep provider-specific logic in adapters. Avoid passing unstructured dictionaries between layers when typed models are appropriate.

## API contracts

`contracts/openapi.yaml` is the authoritative definition of `/api/v1` wire payloads.

Never manually edit:

* `backend/src/app/api/generated/contracts.py`
* `frontend/src/api/generated/openapi.ts`

After contract changes run:

```sh
uv run python scripts/generate_contracts.py
```

Do not duplicate shared API models manually in the backend or frontend.

## Important invariants

Preserve these unless the task explicitly changes them:

* Only one active analysis per session.
* Different sessions may analyze concurrently.
* SSE events are transient; persisted REST state is authoritative.
* Closing the browser does not cancel analysis.
* Rendering should remain deterministic.
* Instruction-set behavior should remain data-driven rather than hard-coded for GDPR, CCPA/CPRA, or other named sets.

## Code quality

Python is strict-mypy and Ruff checked. TypeScript is strict.

Do not weaken type checking or add broad ignores to make code pass.

Avoid unnecessary dependencies and abstractions.

AIADR handles potentially sensitive data. Do not log secrets, credentials, full documents, or unnecessary personal data.

## Validation

Run the relevant checks for your changes.

```sh
uv run ruff check .
uv run mypy main.py backend/src scripts/generate_contracts.py scripts/publish_docx_processor.py

pnpm --dir frontend run typecheck
pnpm --dir frontend run build
```

For DOCX changes:

```sh
dotnet restore docx-processor/Aiadr.Docx.csproj --locked-mode
dotnet build docx-processor/Aiadr.Docx.csproj --no-restore
```

Do not claim a check passed unless it was actually run.

## Change discipline

Fix the underlying problem rather than adding workarounds.

Do not edit generated files directly.

Keep `.env` local and untracked. When adding or removing a supported environment
variable, update the tracked `.env.example` in the same change.

### Versioning

AIADR is continuously developed without releases. Keep the application version at `0.1.0.dev0`; do not bump it for commits, fixes, or features. Keep `pyproject.toml` and OpenAPI `info.version` identical. If the application version is ever changed intentionally, update both, run `uv lock`, and regenerate the API contracts.

Do not manually change `source_revision` or `source_modified`. They are derived from Git. `AIADR_SOURCE_REVISION` is only for build automation that packages AIADR without `.git`; never store a fixed revision in `.env` or source control.

Bump only the identifier owned by the changed compatibility boundary:

* Bump the `/api/v1` generation only for an intentionally incompatible HTTP API contract.
* Bump the SQLite schema version whenever persisted table structure or interpretation changes.
* Bump export and audit-document schema versions whenever their structure, file set, or field meaning changes.
* Bump `DOCX_RENDER_REVISION` whenever DOCX rendering, conversion, effects, or processor behavior could change cached output for the same source and layers.

Instruction sets and the DOCX processor have no independent version. Instruction-set identity is content-hash based; processor changes are identified by `source_revision` and, when output-affecting, `DOCX_RENDER_REVISION`.
