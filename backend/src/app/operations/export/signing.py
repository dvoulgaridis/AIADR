"""HMAC signing helpers for export manifests."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from app.core.config import EXPORT_HMAC_SECRET
from app.core.paths import data_root


def signing_secret() -> str:
    """Return the configured or generated export signing secret."""
    if EXPORT_HMAC_SECRET:
        return EXPORT_HMAC_SECRET
    path = data_root() / "settings" / "export-signing-secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o600)
    return secret


def canonical_json(data: dict[str, object]) -> str:
    """Serialize manifest data canonically for signing."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sign_manifest(manifest: dict[str, object]) -> dict[str, object]:
    """Return a manifest with SHA-256 and HMAC-SHA256 evidence fields."""
    unsigned = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_sha256", "hmac_sha256"}
    }
    unsigned["signing_mode"] = "local-hmac-sha256"
    manifest_sha256 = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    signable = {
        **unsigned,
        "manifest_sha256": manifest_sha256,
    }
    digest = hmac.new(
        signing_secret().encode("utf-8"),
        canonical_json(signable).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        **signable,
        "hmac_sha256": digest,
    }
