"""Transactional persistence for hydrated finding layers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.domain.finding import (
    Finding,
    FindingTarget,
)
from app.domain.layer import Layer
from app.errors import ErrorCode, app_error
from app.sources.kinds import SourceKind
from app.storage import db

_FINDING_INSERT = """
    INSERT INTO findings (
        finding_id, session_id, kind, detected_entity_type, reviewed_entity_type, privacy_category,
        special_category_type, data_subject_context, label, detection_confidence,
        privacy_risk, target_json, description, reason,
        origin, created_by, review_decision, edited, reviewer_note
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_LAYER_INSERT = """
    INSERT INTO layers (
        layer_id, session_id, finding_id, action, effect, effect_source, enabled,
        fill_color, custom_text, note
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_HYDRATED_LAYER_SELECT = """
    SELECT
        f.finding_id AS finding_id,
        f.session_id AS finding_session_id,
        f.kind AS kind,
        f.detected_entity_type AS detected_entity_type,
        f.reviewed_entity_type AS reviewed_entity_type,
        f.privacy_category AS privacy_category,
        f.special_category_type AS special_category_type,
        f.data_subject_context AS data_subject_context,
        f.label AS label,
        f.detection_confidence AS detection_confidence,
        f.privacy_risk AS privacy_risk,
        f.target_json AS target_json,
        f.description AS description,
        f.reason AS reason,
        f.origin AS origin,
        f.created_by AS created_by,
        f.review_decision AS review_decision,
        f.edited AS edited,
        f.reviewer_note AS reviewer_note,
        l.layer_id AS layer_id,
        l.session_id AS layer_session_id,
        l.finding_id AS layer_finding_id,
        l.action AS action,
        l.effect AS effect,
        l.effect_source AS effect_source,
        l.enabled AS enabled,
        l.fill_color AS fill_color,
        l.custom_text AS custom_text,
        l.note AS note
    FROM findings AS f
    LEFT JOIN layers AS l
        ON l.finding_id = f.finding_id
"""

_TARGET_ADAPTER: TypeAdapter[FindingTarget] = TypeAdapter(FindingTarget)


def _target(row: Any) -> FindingTarget:
    try:
        target: FindingTarget = _TARGET_ADAPTER.validate_json(row["target_json"])
        stored_kind = SourceKind(str(row["kind"]))
    except (TypeError, ValueError, ValidationError) as exc:
        raise app_error(
            ErrorCode.REVIEW_INTEGRITY_ERROR,
            details={"finding_id": row["finding_id"], "kind": row["kind"]},
        ) from exc
    if target.kind is not stored_kind:
        raise app_error(
            ErrorCode.REVIEW_INTEGRITY_ERROR,
            details={"finding_id": row["finding_id"], "kind": row["kind"]},
        )
    return target


def _row_to_finding(row: Any) -> Finding:
    return Finding(
        id=row["finding_id"],
        target=_target(row),
        detected_entity_type=row["detected_entity_type"],
        reviewed_entity_type=row["reviewed_entity_type"],
        privacy_category=row["privacy_category"],
        special_category_type=row["special_category_type"],
        data_subject_context=row["data_subject_context"],
        label=row["label"],
        detection_confidence=row["detection_confidence"],
        privacy_risk=row["privacy_risk"],
        description=row["description"],
        reason=row["reason"],
        origin=row["origin"],
        created_by=row["created_by"],
        review_decision=row["review_decision"],
        edited=bool(row["edited"]),
        reviewer_note=row["reviewer_note"],
    )


def _row_to_layer(row: Any) -> Layer:
    finding_id = row["finding_id"]
    layer_id = row["layer_id"]
    if (
        layer_id is None
        or row["layer_finding_id"] != finding_id
        or row["layer_session_id"] != row["finding_session_id"]
    ):
        raise app_error(
            ErrorCode.REVIEW_INTEGRITY_ERROR,
            details={"finding_id": finding_id, "layer_id": layer_id},
        )
    return Layer(
        id=layer_id,
        finding=_row_to_finding(row),
        action=row["action"],
        effect=row["effect"],
        effect_source=row["effect_source"],
        enabled=bool(row["enabled"]),
        fill_color=row["fill_color"],
        custom_text=row["custom_text"],
        note=row["note"],
    )


def _finding_row(session_id: str, finding: Finding) -> tuple[object, ...]:
    return (
        finding.id,
        session_id,
        finding.kind,
        finding.detected_entity_type,
        finding.reviewed_entity_type,
        finding.privacy_category,
        finding.special_category_type,
        finding.data_subject_context,
        finding.label,
        finding.detection_confidence,
        finding.privacy_risk,
        finding.target.model_dump_json(),
        finding.description,
        finding.reason,
        finding.origin,
        finding.created_by,
        finding.review_decision,
        1 if finding.edited else 0,
        finding.reviewer_note,
    )


def _layer_row(session_id: str, layer: Layer) -> tuple[object, ...]:
    return (
        layer.id,
        session_id,
        layer.finding.id,
        layer.action,
        layer.effect,
        layer.effect_source,
        1 if layer.enabled else 0,
        layer.fill_color,
        layer.custom_text,
        layer.note,
    )


def get_layers_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    layer_ids: list[str],
) -> list[Layer]:
    """Return selected layers, or all layers when no IDs are provided."""
    if layer_ids:
        placeholders = ", ".join("?" for _ in layer_ids)
        where = f"f.session_id = ? AND l.session_id = ? AND l.layer_id IN ({placeholders})"
        parameters = (session_id, session_id, *layer_ids)
    else:
        where = "f.session_id = ? OR l.session_id = ?"
        parameters = (session_id, session_id)

    rows = connection.execute(
        f"""
        {_HYDRATED_LAYER_SELECT}
        WHERE {where}
        ORDER BY f.created_at ASC, f.finding_id ASC
        """,
        parameters,
    ).fetchall()
    return [_row_to_layer(row) for row in rows]


def get_layers(session_id: str, layer_ids: list[str]) -> list[Layer]:
    """Return selected layers, or all layers when no IDs are provided."""
    with db.connect() as connection:
        return get_layers_with_connection(connection, session_id, layer_ids)


def get_layer_for_finding_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    finding_id: str,
) -> Layer | None:
    row = connection.execute(
        f"""
        {_HYDRATED_LAYER_SELECT}
        WHERE f.session_id = ? AND f.finding_id = ?
        """,
        (session_id, finding_id),
    ).fetchone()
    return _row_to_layer(row) if row is not None else None


def get_layer_for_finding(session_id: str, finding_id: str) -> Layer | None:
    """Return the layer associated with a finding."""
    with db.connect() as connection:
        return get_layer_for_finding_with_connection(
            connection,
            session_id,
            finding_id,
        )


def _validate_layers(layers: Iterable[Layer]) -> None:
    finding_ids: set[str] = set()
    for layer in layers:
        if layer.finding.id in finding_ids:
            raise app_error(
                ErrorCode.DUPLICATE_FINDING_LAYER,
                details={"finding_id": layer.finding.id},
            )
        finding_ids.add(layer.finding.id)


def replace_layers_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    layers: list[Layer],
) -> None:
    """Replace all findings and layers using the caller's transaction."""
    _validate_layers(layers)
    connection.execute("DELETE FROM layers WHERE session_id = ?", (session_id,))
    connection.execute("DELETE FROM findings WHERE session_id = ?", (session_id,))
    connection.executemany(
        _FINDING_INSERT,
        [_finding_row(session_id, layer.finding) for layer in layers],
    )
    connection.executemany(_LAYER_INSERT, [_layer_row(session_id, layer) for layer in layers])


def add_layer_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    layer: Layer,
) -> Layer:
    _validate_layers([layer])
    connection.execute(_FINDING_INSERT, _finding_row(session_id, layer.finding))
    connection.execute(_LAYER_INSERT, _layer_row(session_id, layer))
    return layer


def _updated_finding_row(finding: Finding, session_id: str) -> tuple[object, ...]:
    row = _finding_row(session_id, finding)
    return (*row[2:], session_id, finding.id)


def save_layer_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    layer: Layer,
) -> Layer:
    """Persist both sides of one hydrated layer using the caller's transaction."""
    finding = layer.finding
    finding_result = connection.execute(
        """
        UPDATE findings SET
            kind = ?, detected_entity_type = ?, reviewed_entity_type = ?, privacy_category = ?,
            special_category_type = ?, data_subject_context = ?, label = ?,
            detection_confidence = ?, privacy_risk = ?,
            target_json = ?, description = ?, reason = ?, origin = ?, created_by = ?,
            review_decision = ?, edited = ?, reviewer_note = ?
        WHERE session_id = ? AND finding_id = ?
        """,
        _updated_finding_row(finding, session_id),
    )
    layer_result = connection.execute(
        """
        UPDATE layers SET
            action = ?, effect = ?, effect_source = ?, enabled = ?, fill_color = ?,
            custom_text = ?, note = ?
        WHERE session_id = ? AND layer_id = ? AND finding_id = ?
        """,
        (
            layer.action,
            layer.effect,
            layer.effect_source,
            1 if layer.enabled else 0,
            layer.fill_color,
            layer.custom_text,
            layer.note,
            session_id,
            layer.id,
            finding.id,
        ),
    )
    if finding_result.rowcount != 1 or layer_result.rowcount != 1:
        raise app_error(
            ErrorCode.REVIEW_INTEGRITY_ERROR,
            details={
                "session_id": session_id,
                "finding_id": finding.id,
                "layer_id": layer.id,
                "finding_rows": finding_result.rowcount,
                "layer_rows": layer_result.rowcount,
            },
        )
    refreshed = get_layers_with_connection(connection, session_id, [layer.id])
    if not refreshed:
        raise app_error(
            ErrorCode.REVIEW_INTEGRITY_ERROR,
            details={"session_id": session_id, "layer_id": layer.id},
        )
    return refreshed[0]
