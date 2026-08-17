"""Gate-specific validation rules.

The validators implement the minimum evidence required to mark each stage gate
as passed. They intentionally validate workflow evidence rather than scientific
claims about any particular heritage tradition.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any


class GateValidationError(ValueError):
    """Raised when a gate record does not satisfy the pass criteria."""


def _require(payload: Mapping[str, Any], field: str) -> Any:
    if field not in payload:
        raise GateValidationError(f"Missing required field: {field}")
    value = payload[field]
    if value is None or value == "" or value == []:
        raise GateValidationError(f"Field must not be empty: {field}")
    return value


def _require_true(payload: Mapping[str, Any], field: str) -> None:
    if payload.get(field) is not True:
        raise GateValidationError(f"Field must be true to pass this gate: {field}")


def _require_positive_number(payload: Mapping[str, Any], field: str) -> float:
    value = _require(payload, field)
    # NaN and infinity survive a naive comparison: `float("nan") <= 0` is False,
    # and infinity is greater than zero. Both would then be recorded as evidence
    # and, in the case of infinity, serialised into an export as a bare
    # `Infinity` literal, which is not valid JSON.
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise GateValidationError(f"Field must be a finite positive number: {field}")
    return float(value)


def _require_score(payload: Mapping[str, Any], field: str) -> float:
    value = _require(payload, field)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 1 <= value <= 5
    ):
        raise GateValidationError(f"Field must be a number from 1 to 5: {field}")
    return float(value)


def validate_gate0(payload: Mapping[str, Any]) -> None:
    status = _require(payload, "permission_status")
    if status not in {"permissible", "restricted", "pending"}:
        raise GateValidationError(
            "permission_status must be permissible, restricted, or pending"
        )
    _require(payload, "rationale")
    _require(payload, "reviewers")
    if status != "permissible":
        raise GateValidationError(
            "Gate 0 can pass only when permission_status is 'permissible'"
        )


def validate_gate1(payload: Mapping[str, Any]) -> None:
    if _require(payload, "authorization_status") != "approved":
        raise GateValidationError("authorization_status must be 'approved'")
    _require(payload, "authorizers")
    _require(payload, "permitted_uses")
    _require(payload, "prohibited_uses")
    _require(payload, "attribution_requirements")
    _require(payload, "revenue_terms")
    _require(payload, "authorization_record_ref")


def validate_gate2(payload: Mapping[str, Any]) -> None:
    _require(payload, "dataset_id")
    _require_positive_number(payload, "source_count")
    _require_true(payload, "technical_metadata_complete")
    _require_true(payload, "cultural_metadata_complete")
    _require(payload, "license_terms")
    _require(payload, "capture_log_ref")


def validate_gate3(payload: Mapping[str, Any]) -> None:
    _require(payload, "library_version")
    _require_positive_number(payload, "elements_count")
    _require_true(payload, "bearer_annotation")
    _require_true(payload, "prohibited_combinations_documented")
    _require(payload, "element_card_schema_ref")


def validate_gate4(payload: Mapping[str, Any]) -> None:
    _require(payload, "model_name")
    _require(payload, "model_version")
    _require(payload, "constraint_method")
    _require_true(payload, "provenance_enabled")
    _require_positive_number(payload, "generated_variants")
    _require(payload, "source_element_ids")
    _require(payload, "generation_log_ref")


def validate_gate5(payload: Mapping[str, Any]) -> None:
    _require_true(payload, "bearer_approved")
    _require_true(payload, "design_expert_approved")
    _require_true(payload, "production_feasible")
    _require(payload, "review_record_ref")
    _require(payload, "reviewers")


def validate_gate6(payload: Mapping[str, Any]) -> None:
    _require_positive_number(payload, "sample_size")
    _require_score(payload, "perceived_authenticity")
    _require_score(payload, "perceived_cultural_value")
    _require_score(payload, "story_comprehension")
    _require_score(payload, "purchase_intention")
    _require_score(payload, "recommendation_intention")
    _require(payload, "test_channel")
    _require(payload, "market_test_report_ref")


def validate_gate7(payload: Mapping[str, Any]) -> None:
    _require_true(payload, "rights_map_current")
    _require_true(payload, "revenue_protocol_active")
    _require_true(payload, "audit_takedown_ready")
    _require(payload, "distribution_records_ref")
    _require(payload, "governance_owner")
    _require(payload, "audit_trail_ref")


VALIDATORS: dict[int, Callable[[Mapping[str, Any]], None]] = {
    0: validate_gate0,
    1: validate_gate1,
    2: validate_gate2,
    3: validate_gate3,
    4: validate_gate4,
    5: validate_gate5,
    6: validate_gate6,
    7: validate_gate7,
}


def validate_gate(gate: int, payload: Mapping[str, Any]) -> None:
    if gate not in VALIDATORS:
        raise GateValidationError(f"Unknown gate: {gate}")
    if not isinstance(payload, Mapping):
        raise GateValidationError("Gate payload must be a JSON object")
    VALIDATORS[gate](payload)
