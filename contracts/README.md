# API Contract

`openapi.yaml` is the sole manually maintained definition of data crossing
`/api/v1`.

Run `uv run python scripts/generate_contracts.py` after changing it. The generated Python
and TypeScript files are committed and must not be edited manually. CI runs the
same generator and fails when its output differs from the committed files.

The contract owns HTTP request, response, path-parameter, error, and event
payloads. It does not own SQLite rows, local paths, provider clients, analysis
runtime objects, rendering behavior, or frontend interaction state.

Global review capabilities and session-bound classification options are separate contract resources.
The frontend extends generated wire types with local UI state; the backend maps internal immutable
instruction-set and review models into those minimal responses.

The model-log response has one stable shape in both runtime modes. Request and
result summaries are always present; the `debug` field is populated only in
development mode and is `null` in normal run mode.
