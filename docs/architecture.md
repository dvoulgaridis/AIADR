## Architecture

- `backend/src/app/api`: HTTP and SSE transport, request validation and API projection
- `backend/src/app/operations`: user-requested workflows and transaction orchestration
- `backend/src/app/domain`: internal immutable values and domain validation
- `backend/src/app/storage`: SQLite queries and persisted-file access
- `backend/src/app/inference`: provider-neutral request preparation, detection, and model diagnostics
- `backend/src/app/adapters`: external API and tool-specific transport
- `backend/src/app/sources`, `preprocessing`, `findings` and `redaction`: source processing
  anchoring and deterministic rendering
- `frontend/src`: Vue interface, session projections, local interaction drafts and transient SSE state
- `docx-processor`: constrained DOCX inspection, text replacement and embedded-image processing
- `contracts/openapi.yaml`: authoritative HTTP contract used to generate backend and frontend types
- `instruction_sets`: portable prompts and policy rules selected for analysis

SQLite files are identified by an AIADR application ID and exact schema version at
startup. Incompatible storage is rejected without changing the database or managed
session files. Compatible databases use write-ahead logging; ordinary connections
enforce foreign keys and a bounded busy timeout.

Permanent session deletion commits the cascading database deletion together with a
durable file-purge instruction. Managed files are then removed idempotently, and
unfinished cleanup is resumed during startup.

All `/api/v1` responses prohibit HTTP storage. Session preview responses are the
deliberate exception: they allow private storage but require revalidation before use.
Compiled WebUI assets are outside this policy.

Export manifests contain a SHA-256 digest of their canonical content and an
HMAC-SHA256 value produced with the configured or installation-local shared secret.
The digest detects manifest changes. The HMAC can be verified only by a party with
the same secret; it is not a public-key signature, and the exported ZIP alone does
not establish independent authenticity. Cross-system verification therefore
requires secure out-of-band sharing of the configured HMAC secret.
