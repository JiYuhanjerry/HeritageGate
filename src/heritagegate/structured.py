"""Normalized v0.3 data entities and structured gate evidence builders."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from . import db


class StructuredDataError(ValueError):
    """Raised when a structured entity is invalid or inconsistent."""


class StructuredReadinessError(StructuredDataError):
    """Raised when normalized records do not yet support a gate transition."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise StructuredDataError(f"Field must be a non-empty string: {field}")
    return value.strip()


def _optional_text(payload: Mapping[str, Any], field: str, default: str = "") -> str:
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise StructuredDataError(f"Field must be a string: {field}")
    return value.strip()


def _choice(payload: Mapping[str, Any], field: str, choices: set[str]) -> str:
    value = _required_text(payload, field)
    if value not in choices:
        raise StructuredDataError(
            f"Field {field} must be one of: {', '.join(sorted(choices))}"
        )
    return value


def _list_of_text(
    payload: Mapping[str, Any], field: str, *, allow_empty: bool = False
) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        requirement = "a list" if allow_empty else "a non-empty list"
        raise StructuredDataError(f"Field must be {requirement}: {field}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise StructuredDataError(f"All values in {field} must be non-empty strings")
        result.append(item.strip())
    return result


def _object(payload: Mapping[str, Any], field: str, *, allow_empty: bool = True) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict) or (not value and not allow_empty):
        requirement = "an object" if allow_empty else "a non-empty object"
        raise StructuredDataError(f"Field must be {requirement}: {field}")
    return dict(value)


def _nonnegative_number(payload: Mapping[str, Any], field: str) -> float:
    value = payload.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise StructuredDataError(f"Field must be a non-negative number: {field}")
    return float(value)


def _positive_integer(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise StructuredDataError(f"Field must be a positive integer: {field}")
    return value


def _nonnegative_integer(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StructuredDataError(f"Field must be a non-negative integer: {field}")
    return value


def _score(payload: Mapping[str, Any], field: str, *, optional: bool = False) -> float | None:
    value = payload.get(field)
    if value is None and optional:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
        raise StructuredDataError(f"Field must be a number from 1 to 5: {field}")
    return float(value)


def _audit(
    conn: sqlite3.Connection,
    project_id: str,
    event_type: str,
    details: Mapping[str, Any],
    *,
    gate: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(project_id, event_type, gate, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, event_type, gate, db.dumps(dict(details)), utc_now()),
    )


ENTITY_ALIASES = {
    "rights-holder": "rights_holders",
    "authorization": "authorization_records",
    "element-card": "cultural_element_cards",
    "model-run": "model_runs",
    "expert-review": "expert_reviews",
    "market-test": "market_tests",
    "revenue-distribution": "revenue_distributions",
}


class StructuredDataManager:
    """CRUD and gate-evidence operations for normalized v0.3 entities."""

    def __init__(self, database: str | Path):
        self.database = db.init_db(database)

    def _require_project(self, conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return row

    def _require_reference(
        self,
        conn: sqlite3.Connection,
        table: str,
        entity_id: str,
        project_id: str,
        label: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND project_id = ?",
            (entity_id, project_id),
        ).fetchone()
        if row is None:
            raise StructuredDataError(
                f"{label} not found in project {project_id}: {entity_id}"
            )
        return row

    def create_entity(
        self, entity_type: str, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        dispatch: dict[str, Callable[[str, Mapping[str, Any]], dict[str, Any]]] = {
            "rights-holder": self.add_rights_holder,
            "authorization": self.add_authorization,
            "element-card": self.add_element_card,
            "model-run": self.add_model_run,
            "expert-review": self.add_expert_review,
            "market-test": self.add_market_test,
            "revenue-distribution": self.add_revenue_distribution,
        }
        if entity_type not in dispatch:
            raise StructuredDataError(f"Unknown entity type: {entity_type}")
        if not isinstance(payload, Mapping):
            raise StructuredDataError("Entity payload must be a JSON object")
        return dispatch[entity_type](project_id, payload)

    def update_entity(
        self,
        entity_type: str,
        project_id: str,
        entity_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update one normalized entity while preserving its identifier.

        The web interface uses this method for browser-based editing. Relationship
        rows (authorization parties, element annotators, and model provenance
        links) are replaced atomically with the submitted values.
        """
        dispatch: dict[str, Callable[[str, str, Mapping[str, Any]], dict[str, Any]]] = {
            "rights-holder": self._update_rights_holder,
            "authorization": self._update_authorization,
            "element-card": self._update_element_card,
            "model-run": self._update_model_run,
            "expert-review": self._update_expert_review,
            "market-test": self._update_market_test,
            "revenue-distribution": self._update_revenue_distribution,
        }
        if entity_type not in dispatch:
            raise StructuredDataError(f"Unknown entity type: {entity_type}")
        if not isinstance(payload, Mapping):
            raise StructuredDataError("Entity payload must be a JSON object")
        supplied_id = payload.get("id")
        if supplied_id not in (None, "", entity_id):
            raise StructuredDataError("Entity id cannot be changed")
        return dispatch[entity_type](project_id, entity_id, payload)

    def _update_rights_holder(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        name = _required_text(payload, "name")
        holder_type = _choice(
            payload,
            "holder_type",
            {
                "bearer", "community", "cultural_authority", "institution",
                "designer", "platform", "producer", "other",
            },
        )
        authority_basis = _required_text(payload, "authority_basis")
        active = payload.get("active", True)
        if not isinstance(active, bool):
            raise StructuredDataError("Field active must be boolean")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_reference(conn, "rights_holders", entity_id, project_id, "Rights holder")
            conn.execute(
                """
                UPDATE rights_holders
                SET name = ?, holder_type = ?, authority_basis = ?, jurisdiction = ?,
                    contact_ref = ?, notes = ?, active = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    name, holder_type, authority_basis,
                    _optional_text(payload, "jurisdiction"),
                    _optional_text(payload, "contact_ref"),
                    _optional_text(payload, "notes"),
                    int(active), now, entity_id, project_id,
                ),
            )
            _audit(conn, project_id, "rights_holder_updated", {"id": entity_id})
        return self.get_entity("rights-holder", entity_id)

    def _normalize_parties(
        self, conn: sqlite3.Connection, project_id: str, payload: Mapping[str, Any]
    ) -> list[tuple[str, str]]:
        parties = payload.get("parties")
        if not isinstance(parties, list) or not parties:
            raise StructuredDataError("Field parties must be a non-empty list")
        normalized: list[tuple[str, str]] = []
        for party in parties:
            if not isinstance(party, Mapping):
                raise StructuredDataError("Each authorization party must be an object")
            holder_id = _required_text(party, "rights_holder_id")
            role = _choice(party, "party_role", {"authorizer", "beneficiary", "representative"})
            holder = self._require_reference(conn, "rights_holders", holder_id, project_id, "Rights holder")
            if not bool(holder["active"]):
                raise StructuredDataError(f"Inactive rights holder cannot authorize: {holder_id}")
            normalized.append((holder_id, role))
        return normalized

    def _update_authorization(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        status = _choice(payload, "status", {"approved", "pending", "restricted", "revoked"})
        permitted = _list_of_text(payload, "permitted_uses")
        prohibited = _list_of_text(payload, "prohibited_uses")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_reference(conn, "authorization_records", entity_id, project_id, "Authorization record")
            parties = self._normalize_parties(conn, project_id, payload)
            conn.execute(
                """
                UPDATE authorization_records
                SET status = ?, permitted_uses_json = ?, prohibited_uses_json = ?,
                    attribution_requirements = ?, revenue_terms = ?, evidence_ref = ?,
                    valid_from = ?, valid_until = ?, signed_at = ?, revoked_at = ?,
                    updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    status, db.dumps(permitted), db.dumps(prohibited),
                    _required_text(payload, "attribution_requirements"),
                    _required_text(payload, "revenue_terms"),
                    _required_text(payload, "evidence_ref"),
                    _optional_text(payload, "valid_from"),
                    _optional_text(payload, "valid_until"),
                    _optional_text(payload, "signed_at"),
                    _optional_text(payload, "revoked_at"),
                    now, entity_id, project_id,
                ),
            )
            conn.execute("DELETE FROM authorization_parties WHERE authorization_id = ?", (entity_id,))
            conn.executemany(
                "INSERT INTO authorization_parties(authorization_id, rights_holder_id, party_role) VALUES (?, ?, ?)",
                [(entity_id, holder_id, role) for holder_id, role in parties],
            )
            _audit(conn, project_id, "authorization_updated", {"id": entity_id, "status": status})
        return self.get_entity("authorization", entity_id)

    def _normalize_annotators(
        self, conn: sqlite3.Connection, project_id: str, payload: Mapping[str, Any]
    ) -> list[tuple[str, str]]:
        annotators = payload.get("annotators")
        if not isinstance(annotators, list) or not annotators:
            raise StructuredDataError("Field annotators must be a non-empty list")
        normalized: list[tuple[str, str]] = []
        for annotator in annotators:
            if not isinstance(annotator, Mapping):
                raise StructuredDataError("Each annotator must be an object")
            holder_id = _required_text(annotator, "rights_holder_id")
            role = _choice(annotator, "annotation_role", {"principal", "co-annotator", "reviewer"})
            self._require_reference(conn, "rights_holders", holder_id, project_id, "Annotator rights holder")
            normalized.append((holder_id, role))
        return normalized

    def _update_element_card(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        permitted = _list_of_text(payload, "permitted_uses")
        prohibited = _list_of_text(payload, "prohibited_uses")
        combinations = _list_of_text(payload, "prohibited_combinations", allow_empty=True)
        technical = _object(payload, "technical_features", allow_empty=False)
        status = _choice(payload, "status", {"draft", "approved", "retired"})
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_reference(conn, "cultural_element_cards", entity_id, project_id, "Cultural element card")
            annotators = self._normalize_annotators(conn, project_id, payload)
            conn.execute(
                """
                UPDATE cultural_element_cards
                SET element_code = ?, name = ?, cultural_meaning = ?, source_ref = ?,
                    attribution_text = ?, permitted_uses_json = ?, prohibited_uses_json = ?,
                    technical_features_json = ?, prohibited_combinations_json = ?,
                    sensitivity_level = ?, status = ?, version = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    _required_text(payload, "element_code"), _required_text(payload, "name"),
                    _required_text(payload, "cultural_meaning"), _required_text(payload, "source_ref"),
                    _required_text(payload, "attribution_text"), db.dumps(permitted),
                    db.dumps(prohibited), db.dumps(technical), db.dumps(combinations),
                    _choice(payload, "sensitivity_level", {"open", "controlled", "restricted", "unknown"}),
                    status, _required_text(payload, "version"), now, entity_id, project_id,
                ),
            )
            conn.execute("DELETE FROM element_annotators WHERE element_card_id = ?", (entity_id,))
            conn.executemany(
                "INSERT INTO element_annotators(element_card_id, rights_holder_id, annotation_role) VALUES (?, ?, ?)",
                [(entity_id, holder_id, role) for holder_id, role in annotators],
            )
            _audit(conn, project_id, "element_card_updated", {"id": entity_id, "status": status})
        return self.get_entity("element-card", entity_id)

    def _normalize_model_run(
        self, conn: sqlite3.Connection, project_id: str, payload: Mapping[str, Any]
    ) -> tuple[list[str], str, int]:
        source_ids = _list_of_text(payload, "source_element_ids")
        run_status = _choice(payload, "run_status", {"completed", "failed", "rejected"})
        output_count = _nonnegative_integer(payload, "output_count")
        if run_status == "completed" and output_count <= 0:
            raise StructuredDataError("A completed model run must have output_count > 0")
        for element_id in source_ids:
            element = self._require_reference(conn, "cultural_element_cards", element_id, project_id, "Cultural element card")
            if run_status == "completed" and element["status"] != "approved":
                raise StructuredDataError(f"Completed model runs may use only approved element cards: {element_id}")
        return source_ids, run_status, output_count

    def _update_model_run(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        with db.connect(self.database) as conn:
            self._require_reference(conn, "model_runs", entity_id, project_id, "Model run")
            source_ids, run_status, output_count = self._normalize_model_run(conn, project_id, payload)
            conn.execute(
                """
                UPDATE model_runs
                SET model_name = ?, model_version = ?, constraint_method = ?, model_ref = ?,
                    parameters_json = ?, output_count = ?, provenance_ref = ?, run_status = ?,
                    started_at = ?, ended_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    _required_text(payload, "model_name"), _required_text(payload, "model_version"),
                    _required_text(payload, "constraint_method"), _optional_text(payload, "model_ref"),
                    db.dumps(_object(payload, "parameters")), output_count,
                    _required_text(payload, "provenance_ref"), run_status,
                    _optional_text(payload, "started_at"), _optional_text(payload, "ended_at"),
                    entity_id, project_id,
                ),
            )
            conn.execute("DELETE FROM model_run_elements WHERE model_run_id = ?", (entity_id,))
            conn.executemany(
                "INSERT INTO model_run_elements(model_run_id, element_card_id) VALUES (?, ?)",
                [(entity_id, element_id) for element_id in source_ids],
            )
            _audit(conn, project_id, "model_run_updated", {"id": entity_id, "status": run_status})
        return self.get_entity("model-run", entity_id)

    def _review_values(self, payload: Mapping[str, Any]) -> tuple[str, str, float | None, float | None, float | None, int | None]:
        role = _choice(
            payload, "reviewer_role",
            {"bearer", "cultural_expert", "design_expert", "production_expert", "legal_expert", "other"},
        )
        decision = _choice(payload, "decision", {"approved", "revise", "rejected"})
        cultural = _score(payload, "cultural_score", optional=True)
        aesthetic = _score(payload, "aesthetic_score", optional=True)
        feasibility = _score(payload, "feasibility_score", optional=True)
        if role in {"bearer", "cultural_expert"} and cultural is None:
            raise StructuredDataError("Bearer/cultural reviews require cultural_score")
        if role == "design_expert" and aesthetic is None:
            raise StructuredDataError("Design reviews require aesthetic_score")
        if role == "production_expert" and feasibility is None:
            raise StructuredDataError("Production reviews require feasibility_score")
        target = payload.get("revision_target_gate")
        if target is not None:
            if not isinstance(target, int) or isinstance(target, bool) or not 0 <= target <= 4:
                raise StructuredDataError("revision_target_gate must be an integer from 0 to 4 or null")
        return role, decision, cultural, aesthetic, feasibility, target

    def _update_expert_review(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        role, decision, cultural, aesthetic, feasibility, target = self._review_values(payload)
        model_run_id = _required_text(payload, "model_run_id")
        reviewer_id = _required_text(payload, "reviewer_rights_holder_id")
        with db.connect(self.database) as conn:
            self._require_reference(conn, "expert_reviews", entity_id, project_id, "Expert review")
            self._require_reference(conn, "model_runs", model_run_id, project_id, "Model run")
            self._require_reference(conn, "rights_holders", reviewer_id, project_id, "Reviewer")
            conn.execute(
                """
                UPDATE expert_reviews
                SET model_run_id = ?, reviewer_rights_holder_id = ?, reviewer_role = ?,
                    cultural_score = ?, aesthetic_score = ?, feasibility_score = ?, decision = ?,
                    comments = ?, revision_target_gate = ?, evidence_ref = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    model_run_id, reviewer_id, role, cultural, aesthetic, feasibility, decision,
                    _optional_text(payload, "comments"), target, _required_text(payload, "evidence_ref"),
                    entity_id, project_id,
                ),
            )
            _audit(conn, project_id, "expert_review_updated", {"id": entity_id, "role": role, "decision": decision})
        return self.get_entity("expert-review", entity_id)

    def _update_market_test(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        model_run_id = _required_text(payload, "model_run_id")
        with db.connect(self.database) as conn:
            self._require_reference(conn, "market_tests", entity_id, project_id, "Market test")
            self._require_reference(conn, "model_runs", model_run_id, project_id, "Model run")
            conn.execute(
                """
                UPDATE market_tests
                SET model_run_id = ?, sample_size = ?, test_channel = ?,
                    perceived_authenticity = ?, perceived_cultural_value = ?,
                    story_comprehension = ?, purchase_intention = ?, recommendation_intention = ?,
                    recommendation = ?, report_ref = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    model_run_id, _positive_integer(payload, "sample_size"),
                    _required_text(payload, "test_channel"), _score(payload, "perceived_authenticity"),
                    _score(payload, "perceived_cultural_value"), _score(payload, "story_comprehension"),
                    _score(payload, "purchase_intention"), _score(payload, "recommendation_intention"),
                    _choice(payload, "recommendation", {"scale", "revise", "discontinue"}),
                    _required_text(payload, "report_ref"), entity_id, project_id,
                ),
            )
            _audit(conn, project_id, "market_test_updated", {"id": entity_id})
        return self.get_entity("market-test", entity_id)

    def _update_revenue_distribution(
        self, project_id: str, entity_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        authorization_id = _required_text(payload, "authorization_id")
        recipient_id = _required_text(payload, "recipient_rights_holder_id")
        gross = _nonnegative_number(payload, "gross_amount")
        share = _nonnegative_number(payload, "share_percent")
        amount = _nonnegative_number(payload, "distributed_amount")
        if share > 100:
            raise StructuredDataError("share_percent must not exceed 100")
        if amount > gross + 1e-9:
            raise StructuredDataError("distributed_amount must not exceed gross_amount")
        currency = _required_text(payload, "currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise StructuredDataError("currency must be a three-letter alphabetic code")
        start = _required_text(payload, "period_start")
        end = _required_text(payload, "period_end")
        if end < start:
            raise StructuredDataError("period_end must not be earlier than period_start")
        with db.connect(self.database) as conn:
            self._require_reference(conn, "revenue_distributions", entity_id, project_id, "Revenue distribution")
            authorization = self._require_reference(conn, "authorization_records", authorization_id, project_id, "Authorization record")
            if authorization["status"] != "approved":
                raise StructuredDataError("Revenue may be distributed only under approved authorization")
            self._require_reference(conn, "rights_holders", recipient_id, project_id, "Revenue recipient")
            existing = conn.execute(
                """
                SELECT MIN(gross_amount) AS gross_amount,
                       COALESCE(SUM(share_percent), 0) AS share_total,
                       COALESCE(SUM(distributed_amount), 0) AS amount_total
                FROM revenue_distributions
                WHERE authorization_id = ? AND currency = ? AND period_start = ? AND period_end = ?
                  AND id <> ?
                """,
                (authorization_id, currency, start, end, entity_id),
            ).fetchone()
            if existing and existing["gross_amount"] is not None:
                if abs(float(existing["gross_amount"]) - gross) > 1e-9:
                    raise StructuredDataError("All distributions in one authorization/currency/period must use the same gross_amount")
                if float(existing["share_total"]) + share > 100 + 1e-9:
                    raise StructuredDataError("Cumulative revenue shares must not exceed 100%")
                if float(existing["amount_total"]) + amount > gross + 1e-9:
                    raise StructuredDataError("Cumulative distributed amount must not exceed gross_amount")
            conn.execute(
                """
                UPDATE revenue_distributions
                SET authorization_id = ?, recipient_rights_holder_id = ?, revenue_category = ?,
                    gross_amount = ?, currency = ?, share_percent = ?, distributed_amount = ?,
                    period_start = ?, period_end = ?, evidence_ref = ?, distributed_at = ?, notes = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    authorization_id, recipient_id,
                    _choice(payload, "revenue_category", {"product", "content_education", "licensing", "digital_ai_service", "other"}),
                    gross, currency, share, amount, start, end,
                    _required_text(payload, "evidence_ref"), _optional_text(payload, "distributed_at"),
                    _optional_text(payload, "notes"), entity_id, project_id,
                ),
            )
            _audit(conn, project_id, "revenue_distribution_updated", {"id": entity_id})
        return self.get_entity("revenue-distribution", entity_id)

    def add_rights_holder(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("holder")
        name = _required_text(payload, "name")
        holder_type = _choice(
            payload,
            "holder_type",
            {
                "bearer",
                "community",
                "cultural_authority",
                "institution",
                "designer",
                "platform",
                "producer",
                "other",
            },
        )
        authority_basis = _required_text(payload, "authority_basis")
        jurisdiction = _optional_text(payload, "jurisdiction")
        contact_ref = _optional_text(payload, "contact_ref")
        notes = _optional_text(payload, "notes")
        active = payload.get("active", True)
        if not isinstance(active, bool):
            raise StructuredDataError("Field active must be boolean")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO rights_holders(
                    id, project_id, name, holder_type, authority_basis,
                    jurisdiction, contact_ref, notes, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    name,
                    holder_type,
                    authority_basis,
                    jurisdiction,
                    contact_ref,
                    notes,
                    int(active),
                    now,
                    now,
                ),
            )
            _audit(conn, project_id, "rights_holder_created", {"id": entity_id})
        return self.get_entity("rights-holder", entity_id)

    def add_authorization(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("auth")
        status = _choice(payload, "status", {"approved", "pending", "restricted", "revoked"})
        permitted_uses = _list_of_text(payload, "permitted_uses")
        prohibited_uses = _list_of_text(payload, "prohibited_uses")
        attribution = _required_text(payload, "attribution_requirements")
        revenue_terms = _required_text(payload, "revenue_terms")
        evidence_ref = _required_text(payload, "evidence_ref")
        parties = payload.get("parties")
        if not isinstance(parties, list) or not parties:
            raise StructuredDataError("Field parties must be a non-empty list")
        normalized_parties: list[tuple[str, str]] = []
        for party in parties:
            if not isinstance(party, Mapping):
                raise StructuredDataError("Each authorization party must be an object")
            holder_id = _required_text(party, "rights_holder_id")
            party_role = _choice(
                party,
                "party_role",
                {"authorizer", "beneficiary", "representative"},
            )
            normalized_parties.append((holder_id, party_role))
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            for holder_id, _ in normalized_parties:
                holder = self._require_reference(
                    conn, "rights_holders", holder_id, project_id, "Rights holder"
                )
                if not bool(holder["active"]):
                    raise StructuredDataError(f"Inactive rights holder cannot authorize: {holder_id}")
            conn.execute(
                """
                INSERT INTO authorization_records(
                    id, project_id, status, permitted_uses_json, prohibited_uses_json,
                    attribution_requirements, revenue_terms, evidence_ref,
                    valid_from, valid_until, signed_at, revoked_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    status,
                    db.dumps(permitted_uses),
                    db.dumps(prohibited_uses),
                    attribution,
                    revenue_terms,
                    evidence_ref,
                    _optional_text(payload, "valid_from"),
                    _optional_text(payload, "valid_until"),
                    _optional_text(payload, "signed_at"),
                    _optional_text(payload, "revoked_at"),
                    now,
                    now,
                ),
            )
            conn.executemany(
                """
                INSERT INTO authorization_parties(
                    authorization_id, rights_holder_id, party_role
                ) VALUES (?, ?, ?)
                """,
                [(entity_id, holder_id, role) for holder_id, role in normalized_parties],
            )
            _audit(conn, project_id, "authorization_created", {"id": entity_id, "status": status})
        return self.get_entity("authorization", entity_id)

    def add_element_card(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("element")
        annotators = payload.get("annotators")
        if not isinstance(annotators, list) or not annotators:
            raise StructuredDataError("Field annotators must be a non-empty list")
        normalized_annotators: list[tuple[str, str]] = []
        for annotator in annotators:
            if not isinstance(annotator, Mapping):
                raise StructuredDataError("Each annotator must be an object")
            holder_id = _required_text(annotator, "rights_holder_id")
            role = _choice(
                annotator,
                "annotation_role",
                {"principal", "co-annotator", "reviewer"},
            )
            normalized_annotators.append((holder_id, role))
        status = _choice(payload, "status", {"draft", "approved", "retired"})
        permitted = _list_of_text(payload, "permitted_uses")
        prohibited = _list_of_text(payload, "prohibited_uses")
        combinations = _list_of_text(payload, "prohibited_combinations", allow_empty=True)
        technical_features = _object(payload, "technical_features", allow_empty=False)
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            for holder_id, _ in normalized_annotators:
                self._require_reference(
                    conn, "rights_holders", holder_id, project_id, "Annotator rights holder"
                )
            conn.execute(
                """
                INSERT INTO cultural_element_cards(
                    id, project_id, element_code, name, cultural_meaning, source_ref,
                    attribution_text, permitted_uses_json, prohibited_uses_json,
                    technical_features_json, prohibited_combinations_json,
                    sensitivity_level, status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    _required_text(payload, "element_code"),
                    _required_text(payload, "name"),
                    _required_text(payload, "cultural_meaning"),
                    _required_text(payload, "source_ref"),
                    _required_text(payload, "attribution_text"),
                    db.dumps(permitted),
                    db.dumps(prohibited),
                    db.dumps(technical_features),
                    db.dumps(combinations),
                    _choice(payload, "sensitivity_level", {"open", "controlled", "restricted", "unknown"}),
                    status,
                    _required_text(payload, "version"),
                    now,
                    now,
                ),
            )
            conn.executemany(
                """
                INSERT INTO element_annotators(
                    element_card_id, rights_holder_id, annotation_role
                ) VALUES (?, ?, ?)
                """,
                [(entity_id, holder_id, role) for holder_id, role in normalized_annotators],
            )
            _audit(conn, project_id, "element_card_created", {"id": entity_id, "status": status})
        return self.get_entity("element-card", entity_id)

    def add_model_run(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("run")
        source_element_ids = _list_of_text(payload, "source_element_ids")
        run_status = _choice(payload, "run_status", {"completed", "failed", "rejected"})
        output_count = _nonnegative_integer(payload, "output_count")
        provenance_ref = _required_text(payload, "provenance_ref")
        if run_status == "completed" and output_count <= 0:
            raise StructuredDataError("A completed model run must have output_count > 0")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            for element_id in source_element_ids:
                element = self._require_reference(
                    conn,
                    "cultural_element_cards",
                    element_id,
                    project_id,
                    "Cultural element card",
                )
                if run_status == "completed" and element["status"] != "approved":
                    raise StructuredDataError(
                        f"Completed model runs may use only approved element cards: {element_id}"
                    )
            conn.execute(
                """
                INSERT INTO model_runs(
                    id, project_id, model_name, model_version, constraint_method,
                    model_ref, parameters_json, output_count, provenance_ref,
                    run_status, started_at, ended_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    _required_text(payload, "model_name"),
                    _required_text(payload, "model_version"),
                    _required_text(payload, "constraint_method"),
                    _optional_text(payload, "model_ref"),
                    db.dumps(_object(payload, "parameters")),
                    output_count,
                    provenance_ref,
                    run_status,
                    _optional_text(payload, "started_at"),
                    _optional_text(payload, "ended_at"),
                    now,
                ),
            )
            conn.executemany(
                "INSERT INTO model_run_elements(model_run_id, element_card_id) VALUES (?, ?)",
                [(entity_id, element_id) for element_id in source_element_ids],
            )
            _audit(conn, project_id, "model_run_created", {"id": entity_id, "status": run_status})
        return self.get_entity("model-run", entity_id)

    def add_expert_review(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("review")
        reviewer_role = _choice(
            payload,
            "reviewer_role",
            {
                "bearer",
                "cultural_expert",
                "design_expert",
                "production_expert",
                "legal_expert",
                "other",
            },
        )
        decision = _choice(payload, "decision", {"approved", "revise", "rejected"})
        cultural_score = _score(payload, "cultural_score", optional=True)
        aesthetic_score = _score(payload, "aesthetic_score", optional=True)
        feasibility_score = _score(payload, "feasibility_score", optional=True)
        if reviewer_role in {"bearer", "cultural_expert"} and cultural_score is None:
            raise StructuredDataError("Bearer/cultural reviews require cultural_score")
        if reviewer_role == "design_expert" and aesthetic_score is None:
            raise StructuredDataError("Design reviews require aesthetic_score")
        if reviewer_role == "production_expert" and feasibility_score is None:
            raise StructuredDataError("Production reviews require feasibility_score")
        revision_target_gate = payload.get("revision_target_gate")
        if revision_target_gate is not None:
            if not isinstance(revision_target_gate, int) or isinstance(revision_target_gate, bool):
                raise StructuredDataError("revision_target_gate must be an integer or null")
            if not 0 <= revision_target_gate <= 4:
                raise StructuredDataError("revision_target_gate must be between 0 and 4")
        now = utc_now()
        model_run_id = _required_text(payload, "model_run_id")
        reviewer_id = _required_text(payload, "reviewer_rights_holder_id")
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            self._require_reference(conn, "model_runs", model_run_id, project_id, "Model run")
            self._require_reference(conn, "rights_holders", reviewer_id, project_id, "Reviewer")
            conn.execute(
                """
                INSERT INTO expert_reviews(
                    id, project_id, model_run_id, reviewer_rights_holder_id,
                    reviewer_role, cultural_score, aesthetic_score, feasibility_score,
                    decision, comments, revision_target_gate, evidence_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    model_run_id,
                    reviewer_id,
                    reviewer_role,
                    cultural_score,
                    aesthetic_score,
                    feasibility_score,
                    decision,
                    _optional_text(payload, "comments"),
                    revision_target_gate,
                    _required_text(payload, "evidence_ref"),
                    now,
                ),
            )
            _audit(
                conn,
                project_id,
                "expert_review_created",
                {"id": entity_id, "role": reviewer_role, "decision": decision},
            )
        return self.get_entity("expert-review", entity_id)

    def add_market_test(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("market")
        model_run_id = _required_text(payload, "model_run_id")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            self._require_reference(conn, "model_runs", model_run_id, project_id, "Model run")
            conn.execute(
                """
                INSERT INTO market_tests(
                    id, project_id, model_run_id, sample_size, test_channel,
                    perceived_authenticity, perceived_cultural_value,
                    story_comprehension, purchase_intention, recommendation_intention,
                    recommendation, report_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    model_run_id,
                    _positive_integer(payload, "sample_size"),
                    _required_text(payload, "test_channel"),
                    _score(payload, "perceived_authenticity"),
                    _score(payload, "perceived_cultural_value"),
                    _score(payload, "story_comprehension"),
                    _score(payload, "purchase_intention"),
                    _score(payload, "recommendation_intention"),
                    _choice(payload, "recommendation", {"scale", "revise", "discontinue"}),
                    _required_text(payload, "report_ref"),
                    now,
                ),
            )
            _audit(conn, project_id, "market_test_created", {"id": entity_id})
        return self.get_entity("market-test", entity_id)

    def add_revenue_distribution(
        self, project_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("distribution")
        authorization_id = _required_text(payload, "authorization_id")
        recipient_id = _required_text(payload, "recipient_rights_holder_id")
        gross_amount = _nonnegative_number(payload, "gross_amount")
        share_percent = _nonnegative_number(payload, "share_percent")
        distributed_amount = _nonnegative_number(payload, "distributed_amount")
        if share_percent > 100:
            raise StructuredDataError("share_percent must not exceed 100")
        if distributed_amount > gross_amount + 1e-9:
            raise StructuredDataError("distributed_amount must not exceed gross_amount")
        currency = _required_text(payload, "currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise StructuredDataError("currency must be a three-letter alphabetic code")
        period_start = _required_text(payload, "period_start")
        period_end = _required_text(payload, "period_end")
        if period_end < period_start:
            raise StructuredDataError("period_end must not be earlier than period_start")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            authorization = self._require_reference(
                conn,
                "authorization_records",
                authorization_id,
                project_id,
                "Authorization record",
            )
            if authorization["status"] != "approved":
                raise StructuredDataError("Revenue may be distributed only under approved authorization")
            self._require_reference(
                conn, "rights_holders", recipient_id, project_id, "Revenue recipient"
            )
            existing = conn.execute(
                """
                SELECT gross_amount, COALESCE(SUM(share_percent), 0) AS share_total,
                       COALESCE(SUM(distributed_amount), 0) AS amount_total
                FROM revenue_distributions
                WHERE authorization_id = ? AND currency = ?
                  AND period_start = ? AND period_end = ?
                """,
                (authorization_id, currency, period_start, period_end),
            ).fetchone()
            if existing and existing["gross_amount"] is not None:
                if abs(float(existing["gross_amount"]) - gross_amount) > 1e-9:
                    raise StructuredDataError(
                        "All distributions in one authorization/currency/period must use the same gross_amount"
                    )
                if float(existing["share_total"]) + share_percent > 100 + 1e-9:
                    raise StructuredDataError("Cumulative revenue shares must not exceed 100%")
                if float(existing["amount_total"]) + distributed_amount > gross_amount + 1e-9:
                    raise StructuredDataError(
                        "Cumulative distributed amount must not exceed gross_amount"
                    )
            conn.execute(
                """
                INSERT INTO revenue_distributions(
                    id, project_id, authorization_id, recipient_rights_holder_id,
                    revenue_category, gross_amount, currency, share_percent,
                    distributed_amount, period_start, period_end, evidence_ref,
                    distributed_at, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    authorization_id,
                    recipient_id,
                    _choice(
                        payload,
                        "revenue_category",
                        {"product", "content_education", "licensing", "digital_ai_service", "other"},
                    ),
                    gross_amount,
                    currency,
                    share_percent,
                    distributed_amount,
                    period_start,
                    period_end,
                    _required_text(payload, "evidence_ref"),
                    _optional_text(payload, "distributed_at"),
                    _optional_text(payload, "notes"),
                    now,
                ),
            )
            _audit(conn, project_id, "revenue_distribution_created", {"id": entity_id})
        return self.get_entity("revenue-distribution", entity_id)

    def configure_governance(
        self, project_id: str, governance_owner: str, audit_takedown_ready: bool
    ) -> dict[str, Any]:
        if not governance_owner.strip():
            raise StructuredDataError("governance_owner must not be empty")
        if not isinstance(audit_takedown_ready, bool):
            raise StructuredDataError("audit_takedown_ready must be boolean")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                UPDATE projects
                SET governance_owner = ?, audit_takedown_ready = ?, updated_at = ?
                WHERE id = ?
                """,
                (governance_owner.strip(), int(audit_takedown_ready), now, project_id),
            )
            _audit(
                conn,
                project_id,
                "governance_configured",
                {
                    "governance_owner": governance_owner.strip(),
                    "audit_takedown_ready": audit_takedown_ready,
                },
            )
        with db.connect(self.database) as conn:
            return dict(self._require_project(conn, project_id))

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        table = ENTITY_ALIASES.get(entity_type)
        if table is None:
            raise StructuredDataError(f"Unknown entity type: {entity_type}")
        with db.connect(self.database) as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entity_id,)).fetchone()
            if row is None:
                raise KeyError(f"{entity_type} not found: {entity_id}")
            return self._expand_row(conn, entity_type, row)

    def list_entities(self, project_id: str, entity_type: str) -> list[dict[str, Any]]:
        table = ENTITY_ALIASES.get(entity_type)
        if table is None:
            raise StructuredDataError(f"Unknown entity type: {entity_type}")
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
            return [self._expand_row(conn, entity_type, row) for row in rows]

    def _expand_row(
        self, conn: sqlite3.Connection, entity_type: str, row: sqlite3.Row
    ) -> dict[str, Any]:
        item = dict(row)
        if "active" in item:
            item["active"] = bool(item["active"])
        json_fields = {
            "authorization": ["permitted_uses_json", "prohibited_uses_json"],
            "element-card": [
                "permitted_uses_json",
                "prohibited_uses_json",
                "technical_features_json",
                "prohibited_combinations_json",
            ],
            "model-run": ["parameters_json"],
        }
        for field in json_fields.get(entity_type, []):
            item[field.removesuffix("_json")] = db.loads(item.pop(field))
        if entity_type == "authorization":
            parties = conn.execute(
                """
                SELECT ap.rights_holder_id, rh.name, rh.holder_type, ap.party_role
                FROM authorization_parties ap
                JOIN rights_holders rh ON rh.id = ap.rights_holder_id
                WHERE ap.authorization_id = ?
                ORDER BY ap.party_role, rh.name
                """,
                (item["id"],),
            ).fetchall()
            item["parties"] = [dict(party) for party in parties]
        elif entity_type == "element-card":
            annotators = conn.execute(
                """
                SELECT ea.rights_holder_id, rh.name, rh.holder_type, ea.annotation_role
                FROM element_annotators ea
                JOIN rights_holders rh ON rh.id = ea.rights_holder_id
                WHERE ea.element_card_id = ?
                ORDER BY ea.annotation_role, rh.name
                """,
                (item["id"],),
            ).fetchall()
            item["annotators"] = [dict(annotator) for annotator in annotators]
        elif entity_type == "model-run":
            elements = conn.execute(
                """
                SELECT c.id, c.element_code, c.name, c.version, c.status
                FROM model_run_elements mre
                JOIN cultural_element_cards c ON c.id = mre.element_card_id
                WHERE mre.model_run_id = ? ORDER BY c.element_code
                """,
                (item["id"],),
            ).fetchall()
            item["source_elements"] = [dict(element) for element in elements]
            item["source_element_ids"] = [element["id"] for element in elements]
        return item

    def build_gate_payload(self, project_id: str, gate: int) -> dict[str, Any]:
        builders: dict[int, Callable[[str], dict[str, Any]]] = {
            1: self._gate1_payload,
            3: self._gate3_payload,
            4: self._gate4_payload,
            5: self._gate5_payload,
            6: self._gate6_payload,
            7: self._gate7_payload,
        }
        if gate not in builders:
            raise StructuredReadinessError(
                "Structured gate construction is available for Gates 1, 3, 4, 5, 6, and 7; "
                "Gates 0 and 2 still use their dedicated gate JSON evidence."
            )
        return builders[gate](project_id)

    def readiness_report(self, project_id: str, gate: int) -> dict[str, Any]:
        try:
            payload = self.build_gate_payload(project_id, gate)
            return {"project_id": project_id, "gate": gate, "ready": True, "payload": payload}
        except (StructuredDataError, KeyError) as exc:
            return {"project_id": project_id, "gate": gate, "ready": False, "reason": str(exc)}

    def _gate1_payload(self, project_id: str) -> dict[str, Any]:
        authorizations = self.list_entities(project_id, "authorization")
        approved = [record for record in authorizations if record["status"] == "approved"]
        if not approved:
            raise StructuredReadinessError("Gate 1 requires at least one approved authorization record")
        authorizers = sorted(
            {
                party["name"]
                for record in approved
                for party in record["parties"]
                if party["party_role"] == "authorizer"
            }
        )
        if not authorizers:
            raise StructuredReadinessError("Approved authorizations require an authorizer party")
        return {
            "authorization_status": "approved",
            "authorizers": authorizers,
            "permitted_uses": sorted({item for record in approved for item in record["permitted_uses"]}),
            "prohibited_uses": sorted({item for record in approved for item in record["prohibited_uses"]}),
            "attribution_requirements": " | ".join(record["attribution_requirements"] for record in approved),
            "revenue_terms": " | ".join(record["revenue_terms"] for record in approved),
            "authorization_record_ref": "structured://authorization-records/" + ",".join(record["id"] for record in approved),
        }

    def _gate3_payload(self, project_id: str) -> dict[str, Any]:
        cards = [
            card
            for card in self.list_entities(project_id, "element-card")
            if card["status"] == "approved"
        ]
        if not cards:
            raise StructuredReadinessError("Gate 3 requires at least one approved cultural-element card")
        for card in cards:
            if not card["prohibited_combinations"]:
                raise StructuredReadinessError(
                    f"Approved card {card['id']} must document prohibited combinations"
                )
            if not any(
                annotator["holder_type"] in {"bearer", "community", "cultural_authority"}
                and annotator["annotation_role"] in {"principal", "co-annotator"}
                for annotator in card["annotators"]
            ):
                raise StructuredReadinessError(
                    f"Approved card {card['id']} lacks bearer/community/cultural-authority annotation"
                )
        versions = sorted({card["version"] for card in cards})
        return {
            "library_version": "+".join(versions),
            "elements_count": len(cards),
            "bearer_annotation": True,
            "prohibited_combinations_documented": True,
            "element_card_schema_ref": "schemas/cultural-element-card.schema.json",
        }

    def _latest_completed_run(self, project_id: str) -> dict[str, Any]:
        runs = [
            run
            for run in self.list_entities(project_id, "model-run")
            if run["run_status"] == "completed"
        ]
        if not runs:
            raise StructuredReadinessError("A completed model run is required")
        return runs[-1]

    def _gate4_payload(self, project_id: str) -> dict[str, Any]:
        run = self._latest_completed_run(project_id)
        if not run["provenance_ref"]:
            raise StructuredReadinessError("Completed model run lacks provenance_ref")
        if not run["source_elements"]:
            raise StructuredReadinessError("Completed model run lacks source cultural elements")
        if any(element["status"] != "approved" for element in run["source_elements"]):
            raise StructuredReadinessError("All model-run source elements must be approved")
        return {
            "model_name": run["model_name"],
            "model_version": run["model_version"],
            "constraint_method": run["constraint_method"],
            "provenance_enabled": True,
            "generated_variants": run["output_count"],
            "source_element_ids": run["source_element_ids"],
            "generation_log_ref": run["provenance_ref"],
        }

    def _gate5_payload(self, project_id: str) -> dict[str, Any]:
        run = self._latest_completed_run(project_id)
        reviews = [
            review
            for review in self.list_entities(project_id, "expert-review")
            if review["model_run_id"] == run["id"]
        ]
        approved_roles = {
            review["reviewer_role"]
            for review in reviews
            if review["decision"] == "approved"
        }
        if not approved_roles.intersection({"bearer", "cultural_expert"}):
            raise StructuredReadinessError("Gate 5 requires an approved bearer or cultural-expert review")
        if "design_expert" not in approved_roles:
            raise StructuredReadinessError("Gate 5 requires an approved design-expert review")
        if "production_expert" not in approved_roles:
            raise StructuredReadinessError("Gate 5 requires an approved production-expert review")
        reviewer_names: list[str] = []
        with db.connect(self.database) as conn:
            for review in reviews:
                if review["decision"] != "approved":
                    continue
                holder = conn.execute(
                    "SELECT name FROM rights_holders WHERE id = ?",
                    (review["reviewer_rights_holder_id"],),
                ).fetchone()
                reviewer_names.append(holder["name"] if holder else review["reviewer_rights_holder_id"])
        return {
            "bearer_approved": True,
            "design_expert_approved": True,
            "production_feasible": True,
            "review_record_ref": "structured://expert-reviews/" + ",".join(review["id"] for review in reviews),
            "reviewers": sorted(set(reviewer_names)),
        }

    def _gate6_payload(self, project_id: str) -> dict[str, Any]:
        tests = self.list_entities(project_id, "market-test")
        if not tests:
            raise StructuredReadinessError("Gate 6 requires at least one structured market test")
        test = tests[-1]
        return {
            "sample_size": test["sample_size"],
            "perceived_authenticity": test["perceived_authenticity"],
            "perceived_cultural_value": test["perceived_cultural_value"],
            "story_comprehension": test["story_comprehension"],
            "purchase_intention": test["purchase_intention"],
            "recommendation_intention": test["recommendation_intention"],
            "test_channel": test["test_channel"],
            "market_test_report_ref": test["report_ref"],
        }

    def _gate7_payload(self, project_id: str) -> dict[str, Any]:
        with db.connect(self.database) as conn:
            project = self._require_project(conn, project_id)
            inactive_parties = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM authorization_parties ap
                JOIN authorization_records ar ON ar.id = ap.authorization_id
                JOIN rights_holders rh ON rh.id = ap.rights_holder_id
                WHERE ar.project_id = ? AND ar.status = 'approved' AND rh.active = 0
                """,
                (project_id,),
            ).fetchone()["n"]
        approved_auths = [
            record
            for record in self.list_entities(project_id, "authorization")
            if record["status"] == "approved"
        ]
        if not approved_auths:
            raise StructuredReadinessError("Gate 7 requires approved authorization records")
        if inactive_parties:
            raise StructuredReadinessError("Rights map contains inactive parties in approved authorizations")
        distributions = self.list_entities(project_id, "revenue-distribution")
        if not distributions:
            raise StructuredReadinessError("Gate 7 requires at least one revenue-distribution record")
        if not project["governance_owner"]:
            raise StructuredReadinessError("Gate 7 requires a configured governance owner")
        if not bool(project["audit_takedown_ready"]):
            raise StructuredReadinessError("Gate 7 requires audit/takedown readiness")
        return {
            "rights_map_current": True,
            "revenue_protocol_active": all(bool(record["revenue_terms"]) for record in approved_auths),
            "audit_takedown_ready": True,
            "distribution_records_ref": "structured://revenue-distributions/" + ",".join(record["id"] for record in distributions),
            "governance_owner": project["governance_owner"],
            "audit_trail_ref": f"structured://audit/{project_id}",
        }

    def export_project_entities(self, project_id: str) -> dict[str, Any]:
        return {
            "rights_holders": self.list_entities(project_id, "rights-holder"),
            "authorization_records": self.list_entities(project_id, "authorization"),
            "cultural_element_cards": self.list_entities(project_id, "element-card"),
            "model_runs": self.list_entities(project_id, "model-run"),
            "expert_reviews": self.list_entities(project_id, "expert-review"),
            "market_tests": self.list_entities(project_id, "market-test"),
            "revenue_distributions": self.list_entities(project_id, "revenue-distribution"),
        }
