"""Real-pilot operations, privacy checks, reproducible statistics, and release readiness.

HeritageGate v0.5 does not verify identity, ethics approval, or the truth of uploaded
records. It provides structure, de-identification safeguards, deterministic analysis,
and publication-preparation outputs that must be reviewed by the study team.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import db
from .version import __version__


class RealPilotError(ValueError):
    """Raised when real-pilot or release data are invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RealPilotError(f"Field must be a non-empty string: {field}")
    return value.strip()


def _optional_text(payload: Mapping[str, Any], field: str, default: str = "") -> str:
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise RealPilotError(f"Field must be a string: {field}")
    return value.strip()


def _choice(payload: Mapping[str, Any], field: str, choices: set[str]) -> str:
    value = _required_text(payload, field)
    if value not in choices:
        raise RealPilotError(f"Field {field} must be one of: {', '.join(sorted(choices))}")
    return value


def _list_of_text(payload: Mapping[str, Any], field: str, *, allow_empty: bool = False) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        requirement = "a list" if allow_empty else "a non-empty list"
        raise RealPilotError(f"Field must be {requirement}: {field}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RealPilotError(f"All values in {field} must be non-empty strings")
        result.append(item.strip())
    return result


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", value))


def _parse_iso(value: str, field: str, *, allow_empty: bool = False) -> str:
    text = value.strip()
    if not text and allow_empty:
        return ""
    if not text:
        raise RealPilotError(f"Field must be an ISO-8601 date or datetime: {field}")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        # Accept calendar dates as well.
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            raise RealPilotError(f"Field must be an ISO-8601 date or datetime: {field}") from exc
    return text


def _json_object_text(value: str, field: str) -> dict[str, Any]:
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RealPilotError(f"Field must be a JSON object: {field}") from exc
    if not isinstance(parsed, dict):
        raise RealPilotError(f"Field must be a JSON object: {field}")
    return parsed


def _json_list_text(value: str, field: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RealPilotError(f"Field must be a JSON list or semicolon-separated list: {field}") from exc
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            raise RealPilotError(f"Field must be a list of strings: {field}")
        return [item.strip() for item in parsed if item.strip()]
    return [item.strip() for item in text.split(";") if item.strip()]


FORBIDDEN_DIRECT_IDENTIFIER_FIELDS = {
    # Names
    "name", "full_name", "fullname", "first_name", "firstname", "last_name",
    "lastname", "given_name", "surname", "family_name", "middle_name",
    "real_name", "legal_name", "nickname", "username", "user_name", "initials",
    # Electronic contact
    "email", "e_mail", "email_address", "mail", "mailbox", "contact_email",
    "phone", "phone_number", "telephone", "tel", "mobile", "mobile_number",
    "cell", "cellphone", "fax", "contact", "contact_info", "contact_number",
    "contact_details", "wechat", "weixin", "whatsapp", "qq", "line_id",
    "telegram", "skype", "twitter", "instagram", "social_handle",
    # Postal and geographic
    "address", "postal_address", "home_address", "street", "street_address",
    "postcode", "postal_code", "zip", "zip_code", "city_of_residence",
    # Government and institutional identifiers
    "national_id", "nationalid", "id_card", "idcard", "id_number", "identity_card",
    "citizen_id", "passport", "passport_number", "ssn", "social_security",
    "social_security_number", "nino", "nhs_number", "tax_id", "driver_license",
    "student_id", "student_number", "staff_id", "employee_id", "employee_number",
    "matriculation_number", "enrolment_number", "enrollment_number",
    # Dates and biometrics
    "birth_date", "birthdate", "date_of_birth", "dob", "birthday",
    "photo", "photograph", "avatar", "portrait", "signature", "fingerprint",
    "face_image", "voice_sample",
    # Device and network identifiers
    "ip", "ip_address", "mac_address", "device_id", "imei", "uuid_device",
    "session_cookie", "account_id", "login",
}

# High-signal fragments. A normalized header containing one of these is refused
# even when the full string is not in the exact set, which catches variants such
# as "contact_email_2", "guardian_phone", or "participant_passport_no".
FORBIDDEN_IDENTIFIER_SUBSTRINGS = (
    "email", "e_mail", "mailbox", "phone", "telephone", "mobile_number",
    "cellphone", "full_name", "first_name", "last_name", "given_name",
    "family_name", "real_name", "legal_name", "surname", "nickname",
    "postal_address", "home_address", "street_address", "postcode",
    "postal_code", "zip_code", "national_id", "id_card", "identity_card",
    "citizen_id", "passport", "social_security", "student_id", "student_number",
    "staff_id", "employee_id", "driver_license", "date_of_birth", "birth_date",
    "birthday", "fingerprint", "ip_address", "mac_address", "device_id",
    "wechat", "whatsapp", "telegram",
)

# Non-ASCII headers are common in practice and are not reachable by the
# ASCII-oriented rules above. Matching is by substring because these terms are
# frequently embedded in longer labels.
FORBIDDEN_IDENTIFIER_CJK_SUBSTRINGS = (
    "姓名", "名字", "全名", "真实姓名", "昵称", "称呼",
    "手机", "电话", "联系电话", "联系方式", "联系人",
    "邮箱", "电子邮箱", "邮件地址", "电邮",
    "地址", "住址", "家庭住址", "通讯地址", "邮编",
    "身份证", "证件号", "证件号码", "护照", "社保号",
    "学号", "工号", "职工号", "准考证",
    "生日", "出生日期", "出生年月",
    "微信", "微信号", "签名", "照片", "头像", "指纹",
)


# Columns the participant importer reads. Anything else is discarded, and the
# import batch records the discard so it is visible rather than silent.
RECOGNIZED_PARTICIPANT_COLUMNS = {
    "source_id", "participant_role", "experience_level", "consent_status",
    "consented_at", "eligibility_status", "demographics_json",
    "data_use_scope_json", "notes",
}


def _normalize_field_name(key: Any) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def identifier_rule_for(normalized: str) -> str | None:
    """Return the matched rule name if a normalized field name is a direct identifier.

    Matching is layered: an exact match on a known field name, an ASCII
    substring match for common variants, then a CJK substring match. The
    function returns which rule fired so that callers can explain the refusal
    rather than only reporting that one occurred.
    """
    if not normalized:
        return None
    if normalized in FORBIDDEN_DIRECT_IDENTIFIER_FIELDS:
        return "exact"
    for fragment in FORBIDDEN_IDENTIFIER_SUBSTRINGS:
        if fragment in normalized:
            return f"contains:{fragment}"
    for fragment in FORBIDDEN_IDENTIFIER_CJK_SUBSTRINGS:
        if fragment in normalized:
            return f"contains:{fragment}"
    return None


def is_direct_identifier_field(name: Any) -> bool:
    return identifier_rule_for(_normalize_field_name(name)) is not None


def _scan_identifier_keys(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if identifier_rule_for(_normalize_field_name(key)) is not None:
                found.append(path)
            found.extend(_scan_identifier_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_scan_identifier_keys(child, f"{prefix}[{index}]"))
    return found


def _audit(conn: Any, project_id: str, event_type: str, details: Mapping[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(project_id, event_type, gate, details_json, created_at)
        VALUES (?, ?, NULL, ?, ?)
        """,
        (project_id, event_type, db.dumps(dict(details)), utc_now()),
    )


REAL_PILOT_ENTITY_ALIASES = {
    "consent-document": "consent_documents",
    "import-batch": "participant_import_batches",
    "enrollment": "participant_enrollments",
    "quality-run": "data_quality_runs",
    "analysis-run": "analysis_runs",
    "release-profile": "release_profiles",
}


RUN_CONTEXT_FILENAME = "analysis_run_context.json"

IDENTITY_SCHEME_LEGACY = "sha256-project-v0"
IDENTITY_SCHEME_KEYED = "hmac-sha256-v1"
IDENTITY_SCHEME_METADATA_KEY = "identity_hash_scheme"
IDENTITY_KEY_FINGERPRINT_KEY = "identity_key_fingerprint"
PEPPER_ENV_VAR = "HERITAGEGATE_IDENTITY_KEY_FILE"


class RealPilotManager:
    """Manage de-identified enrollment, data quality, analysis, and release metadata."""

    ANALYSIS_VERSION = "0.5.0"

    def __init__(self, database: str | Path):
        self.database = db.init_db(database)
        self._scheme_cache: str | None = None
        self._key_cache: bytes | None = None

    # ------------------------------------------------------------------
    # Participant pseudonymization
    #
    # Participant codes are derived from a local source identifier. Under the
    # original scheme the derivation was sha256(project_id | source_id), whose
    # only salt was a public project identifier; because roster identifiers are
    # low-entropy strings, a candidate identifier could be confirmed by
    # recomputation in negligible time. The keyed scheme below replaces that
    # with HMAC-SHA-256 under a per-database secret held outside the database,
    # so possession of the database alone no longer permits confirmation.
    #
    # Databases that already contain enrollments keep the legacy scheme, since
    # changing the derivation would orphan every existing participant code.
    # ------------------------------------------------------------------

    def identity_key_path(self) -> Path:
        """Location of the secret used for keyed pseudonymization."""
        import os

        override = os.environ.get(PEPPER_ENV_VAR, "").strip()
        if override:
            return Path(override).expanduser().resolve()
        text = str(self.database)
        # db.init_db resolves ":memory:" to a literal file of that name rather
        # than opening an in-memory database, so the sentinel survives as the
        # final path component. Deriving a key beside it would leave a
        # confusingly named file in the working directory.
        if Path(text).name in {":memory:", ""} or text.startswith("file:"):
            raise RealPilotError(
                "Keyed pseudonymization needs a key file with a stable location, and "
                f"'{text}' does not provide one. Set {PEPPER_ENV_VAR} to an explicit "
                "path, or use a named database file."
            )
        return Path(text + ".key")

    def _load_identity_key(self) -> bytes:
        import os
        import secrets

        if self._key_cache is not None:
            return self._key_cache
        path = self.identity_key_path()
        if path.exists():
            material = path.read_text(encoding="utf-8").strip()
            if not material:
                raise RealPilotError(
                    f"Identity key file is empty: {path}. Restore it from your secret store; "
                    "participant codes cannot be reproduced without it."
                )
            self._key_cache = material.encode("utf-8")
            self._verify_key_fingerprint(self._key_cache)
            return self._key_cache
        path.parent.mkdir(parents=True, exist_ok=True)
        # A database that already records a fingerprint was created with a key
        # that is now missing — typically the database was copied or moved
        # without it. Generating a fresh key here would write a file that looks
        # authoritative but derives different codes for the same people, so
        # refuse before creating anything.
        with db.connect(self.database) as conn:
            recorded = conn.execute(
                "SELECT value FROM schema_metadata WHERE key = ?",
                (IDENTITY_KEY_FINGERPRINT_KEY,),
            ).fetchone()
        if recorded is not None and recorded["value"]:
            raise RealPilotError(
                f"Identity key file is missing: {path}. This database was created with a "
                "key that is not present, so participant codes cannot be reproduced. "
                "Restore the original key from your secret store, or point "
                f"{PEPPER_ENV_VAR} at it."
            )
        material = secrets.token_hex(32)
        path.write_text(material + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except (OSError, NotImplementedError):
            # Windows and some mounted filesystems do not honour POSIX modes.
            # The key is still written; file-system permissions are the
            # deployment's responsibility there.
            pass
        self._key_cache = material.encode("utf-8")
        self._verify_key_fingerprint(self._key_cache)
        return self._key_cache

    def identity_scheme(self) -> str:
        """Return the pseudonymization scheme in force for this database.

        The scheme is immutable once recorded, so it is cached per manager
        instance. Without the cache a bulk import opens two extra database
        connections per row, because both the identity hash and the row digest
        consult it.
        """
        if self._scheme_cache is not None:
            return self._scheme_cache
        with db.connect(self.database) as conn:
            row = conn.execute(
                "SELECT value FROM schema_metadata WHERE key = ?",
                (IDENTITY_SCHEME_METADATA_KEY,),
            ).fetchone()
            if row is not None and row["value"]:
                self._scheme_cache = str(row["value"])
                return self._scheme_cache
            existing = conn.execute(
                "SELECT COUNT(*) AS n FROM participant_enrollments"
            ).fetchone()["n"]
            scheme = IDENTITY_SCHEME_LEGACY if existing else IDENTITY_SCHEME_KEYED
            conn.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES (?, ?)",
                (IDENTITY_SCHEME_METADATA_KEY, scheme),
            )
        self._scheme_cache = scheme
        return scheme

    def _verify_key_fingerprint(self, key: bytes) -> None:
        """Detect a substituted or restored-from-wrong-backup key.

        A different key silently produces different participant codes, so the
        same person can be enrolled twice with nothing to link the records. A
        fingerprint over a fixed constant is recorded on first use and checked
        afterwards; it reveals nothing about the key itself.
        """
        import hmac

        fingerprint = hmac.new(key, b"heritagegate-key-fingerprint-v1", hashlib.sha256).hexdigest()
        with db.connect(self.database) as conn:
            row = conn.execute(
                "SELECT value FROM schema_metadata WHERE key = ?",
                (IDENTITY_KEY_FINGERPRINT_KEY,),
            ).fetchone()
            if row is None or not row["value"]:
                conn.execute(
                    "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES (?, ?)",
                    (IDENTITY_KEY_FINGERPRINT_KEY, fingerprint),
                )
                return
            if str(row["value"]) != fingerprint:
                raise RealPilotError(
                    "Identity key does not match the key this database was created with. "
                    f"Restore the original key file ({self.identity_key_path()}) from your "
                    "secret store. Continuing with a different key would derive new "
                    "participant codes for people who are already enrolled."
                )

    def _row_digest(self, project_id: str, canonical_row: str) -> str:
        """Digest of a source row, keyed under the same scheme as identities.

        The row text contains the source identifier and every other supplied
        value, so an unkeyed digest of it would be open to the same
        confirmation attack the identity hash is protected against.
        """
        if self.identity_scheme() == IDENTITY_SCHEME_LEGACY:
            return _sha256_text(canonical_row)
        import hmac

        return hmac.new(
            self._load_identity_key(),
            f"row|{project_id}|{canonical_row}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _identity_hash(self, project_id: str, source_token: str) -> str:
        token = f"{project_id}|{source_token}"
        if self.identity_scheme() == IDENTITY_SCHEME_LEGACY:
            return _sha256_text(token)
        import hmac

        return hmac.new(
            self._load_identity_key(), token.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _require_project(self, conn: Any, project_id: str) -> Any:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return row

    def register_consent_document(
        self,
        project_id: str,
        *,
        document_path: str | Path,
        title: str,
        version: str,
        language: str,
        ethics_ref: str,
        effective_from: str,
        withdrawal_contact: str,
        retention_policy: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        path = Path(document_path).expanduser().resolve()
        if not path.is_file():
            raise RealPilotError(f"Consent document not found: {path}")
        if not title.strip() or not version.strip() or not language.strip():
            raise RealPilotError("Consent title, version, and language are required")
        if not withdrawal_contact.strip() or not retention_policy.strip():
            raise RealPilotError("Withdrawal contact and retention policy are required")
        effective = _parse_iso(effective_from, "effective_from")
        entity_id = document_id or _new_id("consent")
        now = utc_now()
        digest = _sha256_bytes(path.read_bytes())
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO consent_documents(
                    id, project_id, document_title, document_version, language,
                    ethics_ref, body_ref, body_sha256, effective_from,
                    withdrawal_contact, retention_policy, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id, project_id, title.strip(), version.strip(), language.strip(),
                    ethics_ref.strip(), str(path), digest, effective,
                    withdrawal_contact.strip(), retention_policy.strip(), now,
                ),
            )
            _audit(conn, project_id, "consent_document_registered", {
                "id": entity_id, "document_version": version.strip(), "body_sha256": digest
            })
        return self.get_entity("consent-document", entity_id)

    def add_consent_document(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entity_id = _optional_text(payload, "id") or _new_id("consent")
        body_ref = _required_text(payload, "body_ref")
        digest = _required_text(payload, "body_sha256").lower()
        if not _is_sha256(digest):
            raise RealPilotError("body_sha256 must contain 64 hexadecimal characters")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO consent_documents(
                    id, project_id, document_title, document_version, language,
                    ethics_ref, body_ref, body_sha256, effective_from,
                    withdrawal_contact, retention_policy, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id, project_id, _required_text(payload, "document_title"),
                    _required_text(payload, "document_version"), _required_text(payload, "language"),
                    _optional_text(payload, "ethics_ref"), body_ref, digest,
                    _parse_iso(_required_text(payload, "effective_from"), "effective_from"),
                    _required_text(payload, "withdrawal_contact"),
                    _required_text(payload, "retention_policy"), now,
                ),
            )
            _audit(conn, project_id, "consent_document_registered", {"id": entity_id})
        return self.get_entity("consent-document", entity_id)

    def import_participants_csv(
        self,
        project_id: str,
        csv_path: str | Path,
        *,
        consent_document_id: str | None = None,
        participant_prefix: str = "P",
    ) -> dict[str, Any]:
        path = Path(csv_path).expanduser().resolve()
        if not path.is_file():
            raise RealPilotError(f"Participant CSV not found: {path}")
        raw = path.read_bytes()
        digest = _sha256_bytes(raw)
        batch_id = _new_id("import")
        imported = 0
        rejected = 0
        duplicates = 0
        rejected_rows: list[dict[str, Any]] = []
        now = utc_now()
        # Create the batch before enrollments so SQLite foreign-key checks remain valid.
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO participant_import_batches(
                    id, project_id, source_name, source_sha256,
                    imported_count, rejected_count, duplicate_count,
                    mapping_json, rejected_rows_json, created_at
                ) VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?)
                """,
                (batch_id, project_id, path.name, digest, db.dumps({}), db.dumps([]), now),
            )

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]
            normalized_headers = {_normalize_field_name(h) for h in headers}
            forbidden = sorted(
                f"{h} ({identifier_rule_for(_normalize_field_name(h))})"
                for h in headers
                if identifier_rule_for(_normalize_field_name(h)) is not None
            )
            if forbidden:
                raise RealPilotError(
                    "Participant import refuses direct-identifier columns: " + ", ".join(forbidden)
                )
            required = {"source_id", "participant_role", "experience_level", "consent_status"}
            missing = sorted(required - normalized_headers)
            if missing:
                raise RealPilotError("Participant CSV is missing required columns: " + ", ".join(missing))
            # Columns outside the recognized set are silently dropped by the row
            # parser below. Silence is the hazard: a researcher who supplies an
            # unrecognized identifier column would otherwise believe the file
            # had been reviewed and accepted. Record them so the batch, the CLI,
            # and the audit trail all state what was discarded.
            dropped_columns = sorted(
                h for h in headers if _normalize_field_name(h) not in RECOGNIZED_PARTICIPANT_COLUMNS
            )
            warnings = [
                "Unrecognized columns were not imported and their values were discarded: "
                + ", ".join(dropped_columns)
                + ". Confirm that none of them carried a direct identifier."
            ] if dropped_columns else []

            with db.connect(self.database) as conn:
                self._require_project(conn, project_id)
                if consent_document_id:
                    consent = conn.execute(
                        "SELECT * FROM consent_documents WHERE id = ? AND project_id = ?",
                        (consent_document_id, project_id),
                    ).fetchone()
                    if consent is None:
                        raise RealPilotError(f"Consent document not found: {consent_document_id}")

            for row_number, original_row in enumerate(reader, start=2):
                row = {str(k).strip().lower().replace("-", "_").replace(" ", "_"): (v or "").strip()
                       for k, v in original_row.items() if k is not None}
                source_id = row.get("source_id", "")
                source_hash = self._identity_hash(project_id, source_id) if source_id else ""
                try:
                    if not source_id:
                        raise RealPilotError("source_id is required")
                    role = row.get("participant_role", "")
                    if role not in {"researcher", "bearer", "cultural_expert", "designer", "developer", "student", "other"}:
                        raise RealPilotError("participant_role is invalid")
                    experience = row.get("experience_level", "")
                    if experience not in {"novice", "intermediate", "advanced"}:
                        raise RealPilotError("experience_level is invalid")
                    consent_status = row.get("consent_status", "")
                    if consent_status not in {"consented", "exempt", "withdrawn"}:
                        raise RealPilotError("consent_status is invalid")
                    eligibility = row.get("eligibility_status", "eligible") or "eligible"
                    if eligibility not in {"eligible", "ineligible", "pending"}:
                        raise RealPilotError("eligibility_status is invalid")
                    consented_at = row.get("consented_at", "")
                    if consent_status == "consented":
                        if not consent_document_id:
                            raise RealPilotError("consented rows require a registered consent document")
                        consented_at = _parse_iso(consented_at, "consented_at")
                    elif consented_at:
                        consented_at = _parse_iso(consented_at, "consented_at")
                    demographics = _json_object_text(row.get("demographics_json", "{}"), "demographics_json")
                    forbidden_keys = _scan_identifier_keys(demographics)
                    if forbidden_keys:
                        raise RealPilotError(
                            "demographics_json contains direct-identifier keys: " + ", ".join(forbidden_keys)
                        )
                    data_scope = _json_list_text(row.get("data_use_scope_json", "[]"), "data_use_scope_json")
                    if not data_scope:
                        data_scope = ["pilot_analysis"]
                    identity_hash = source_hash
                    participant_id = f"participant-{identity_hash[:16]}"
                    participant_code = f"{participant_prefix}-{identity_hash[:10].upper()}"
                    enrollment_id = f"enrollment-{identity_hash[:16]}"
                    source_row_hash = self._row_digest(project_id, json.dumps(row, ensure_ascii=False, sort_keys=True))
                    now = utc_now()
                    with db.connect(self.database) as conn:
                        self._require_project(conn, project_id)
                        existing = conn.execute(
                            "SELECT id FROM participant_enrollments WHERE project_id = ? AND identity_token_hash = ?",
                            (project_id, identity_hash),
                        ).fetchone()
                        if existing is not None:
                            duplicates += 1
                            continue
                        consent_ref = f"consent-document:{consent_document_id}" if consent_status == "consented" else ""
                        demographics = dict(demographics)
                        demographics["deidentified"] = True
                        conn.execute(
                            """
                            INSERT INTO pilot_participants(
                                id, project_id, participant_code, participant_role,
                                experience_level, consent_status, consent_ref,
                                demographics_json, notes, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                participant_id, project_id, participant_code, role, experience,
                                consent_status, consent_ref, db.dumps(demographics),
                                row.get("notes", ""), now,
                            ),
                        )
                        conn.execute(
                            """
                            INSERT INTO participant_enrollments(
                                id, project_id, participant_id, consent_document_id,
                                import_batch_id, eligibility_status, consented_at, withdrawn_at,
                                identity_token_hash, source_row_hash, data_use_scope_json,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                enrollment_id, project_id, participant_id, consent_document_id,
                                batch_id, eligibility, consented_at,
                                consented_at if consent_status == "withdrawn" else "",
                                identity_hash, source_row_hash, db.dumps(data_scope), now, now,
                            ),
                        )
                        _audit(conn, project_id, "participant_anonymously_imported", {
                            "participant_id": participant_id,
                            "participant_code": participant_code,
                            "source_hash_prefix": identity_hash[:12],
                            "batch_id": batch_id,
                        })
                    imported += 1
                except Exception as exc:  # record sanitized row-level errors and continue
                    rejected += 1
                    rejected_rows.append({
                        "row_number": row_number,
                        "source_hash_prefix": source_hash[:12] if source_hash else "",
                        "reason": str(exc),
                    })

        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            conn.execute(
                """
                UPDATE participant_import_batches
                SET imported_count = ?, rejected_count = ?, duplicate_count = ?,
                    mapping_json = ?, rejected_rows_json = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    imported, rejected, duplicates,
                    db.dumps({
                        "headers": headers,
                        "participant_prefix": participant_prefix,
                        "dropped_columns": dropped_columns,
                        "warnings": warnings,
                    }),
                    db.dumps(rejected_rows), batch_id, project_id,
                ),
            )
            _audit(conn, project_id, "participant_import_completed", {
                "batch_id": batch_id, "imported": imported, "rejected": rejected,
                "duplicates": duplicates, "source_sha256": digest,
                "dropped_columns": dropped_columns,
            })
        return self.get_entity("import-batch", batch_id)

    def enroll_existing_participant(
        self,
        project_id: str,
        participant_id: str,
        *,
        source_token: str,
        consent_document_id: str | None = None,
        eligibility_status: str = "eligible",
        consented_at: str = "",
        data_use_scope: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add a privacy-preserving enrollment to an existing de-identified participant."""
        if not source_token.strip():
            raise RealPilotError("source_token is required and is hashed rather than stored")
        if eligibility_status not in {"eligible", "ineligible", "pending"}:
            raise RealPilotError("eligibility_status is invalid")
        scope = data_use_scope or ["pilot_analysis"]
        if any(not isinstance(item, str) or not item.strip() for item in scope):
            raise RealPilotError("data_use_scope must contain non-empty strings")
        identity_hash = self._identity_hash(project_id, source_token.strip())
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            participant = conn.execute(
                "SELECT * FROM pilot_participants WHERE id = ? AND project_id = ?",
                (participant_id, project_id),
            ).fetchone()
            if participant is None:
                raise RealPilotError(f"Participant not found: {participant_id}")
            # Surface a domain error rather than letting the UNIQUE constraint
            # escape as sqlite3.IntegrityError, which callers cannot handle
            # meaningfully and which leaks the storage layer through the API.
            existing = conn.execute(
                "SELECT id FROM participant_enrollments WHERE project_id = ? AND participant_id = ?",
                (project_id, participant_id),
            ).fetchone()
            if existing is not None:
                raise RealPilotError(
                    f"Participant is already enrolled: {participant_id} (enrollment {existing['id']})"
                )
            if participant["consent_status"] == "consented":
                if not consent_document_id:
                    raise RealPilotError("Consented participants require consent_document_id")
                if not consented_at:
                    raise RealPilotError("Consented participants require consented_at")
            if consent_document_id:
                doc = conn.execute(
                    "SELECT id FROM consent_documents WHERE id = ? AND project_id = ?",
                    (consent_document_id, project_id),
                ).fetchone()
                if doc is None:
                    raise RealPilotError(f"Consent document not found: {consent_document_id}")
            parsed_consent = _parse_iso(consented_at, "consented_at", allow_empty=True)
            entity_id = f"enrollment-{identity_hash[:16]}"
            row_hash = self._row_digest(project_id, json.dumps({
                "participant_id": participant_id,
                "consent_document_id": consent_document_id,
                "eligibility_status": eligibility_status,
                "consented_at": parsed_consent,
                "data_use_scope": scope,
            }, sort_keys=True))
            conn.execute(
                """
                INSERT INTO participant_enrollments(
                    id, project_id, participant_id, consent_document_id,
                    import_batch_id, eligibility_status, consented_at, withdrawn_at,
                    identity_token_hash, source_row_hash, data_use_scope_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, '', ?, ?, ?, ?, ?)
                """,
                (
                    entity_id, project_id, participant_id, consent_document_id,
                    eligibility_status, parsed_consent, identity_hash, row_hash,
                    db.dumps([item.strip() for item in scope]), now, now,
                ),
            )
            _audit(conn, project_id, "participant_enrolled", {
                "participant_id": participant_id,
                "enrollment_id": entity_id,
                "source_hash_prefix": identity_hash[:12],
            })
        return self.get_entity("enrollment", entity_id)

    def withdraw_participant(self, project_id: str, participant_id: str, *, withdrawn_at: str, reason: str) -> dict[str, Any]:
        when = _parse_iso(withdrawn_at, "withdrawn_at")
        if not reason.strip():
            raise RealPilotError("Withdrawal reason is required")
        now = utc_now()
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            participant = conn.execute(
                "SELECT * FROM pilot_participants WHERE id = ? AND project_id = ?",
                (participant_id, project_id),
            ).fetchone()
            if participant is None:
                raise RealPilotError(f"Participant not found: {participant_id}")
            enrollment = conn.execute(
                "SELECT * FROM participant_enrollments WHERE participant_id = ? AND project_id = ?",
                (participant_id, project_id),
            ).fetchone()
            if enrollment is None:
                raise RealPilotError("Participant has no v0.5 enrollment record")
            conn.execute(
                "UPDATE pilot_participants SET consent_status = 'withdrawn' WHERE id = ?",
                (participant_id,),
            )
            conn.execute(
                "UPDATE participant_enrollments SET withdrawn_at = ?, updated_at = ? WHERE participant_id = ?",
                (when, now, participant_id),
            )
            _audit(conn, project_id, "participant_withdrawn", {
                "participant_id": participant_id, "withdrawn_at": when, "reason": reason.strip()
            })
        return self.get_entity("enrollment", enrollment["id"])

    def upsert_release_profile(self, project_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        authors = payload.get("authors")
        if not isinstance(authors, list) or not authors:
            raise RealPilotError("authors must be a non-empty list")
        for index, author in enumerate(authors):
            if not isinstance(author, Mapping) or not str(author.get("name", "")).strip():
                raise RealPilotError(f"authors[{index}] must contain a non-empty name")
        keywords = _list_of_text(payload, "keywords")
        support_email = _optional_text(payload, "support_email")
        if support_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", support_email):
            raise RealPilotError("support_email is not a valid email address")
        license_spdx = _required_text(payload, "license_spdx")
        entity_id = _optional_text(payload, "id") or f"release-{project_id}"
        now = utc_now()
        values = (
            entity_id, project_id, _required_text(payload, "software_title"),
            _required_text(payload, "manuscript_title"), _required_text(payload, "software_version"),
            _choice(payload, "release_status", {"draft", "candidate", "released"}),
            _choice(payload, "evidence_status", {"synthetic", "real_pilot", "validated_real_pilot"}),
            _optional_text(payload, "repository_url"), _optional_text(payload, "archive_url"),
            _optional_text(payload, "software_doi"), _optional_text(payload, "executable_url"),
            _optional_text(payload, "documentation_url"), support_email, license_spdx,
            db.dumps([dict(author) for author in authors]), db.dumps(keywords),
            _optional_text(payload, "release_date"), _optional_text(payload, "funding_statement"),
            _optional_text(payload, "conflict_statement"), _optional_text(payload, "ai_use_statement"),
            _optional_text(payload, "data_availability_statement"), now, now,
        )
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            existing = conn.execute("SELECT id, created_at FROM release_profiles WHERE project_id = ?", (project_id,)).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO release_profiles(
                        id, project_id, software_title, manuscript_title, software_version,
                        release_status, evidence_status, repository_url, archive_url,
                        software_doi, executable_url, documentation_url, support_email,
                        license_spdx, authors_json, keywords_json, release_date,
                        funding_statement, conflict_statement, ai_use_statement,
                        data_availability_statement, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                event = "release_profile_created"
            else:
                conn.execute(
                    """
                    UPDATE release_profiles SET
                        software_title = ?, manuscript_title = ?, software_version = ?,
                        release_status = ?, evidence_status = ?, repository_url = ?, archive_url = ?,
                        software_doi = ?, executable_url = ?, documentation_url = ?, support_email = ?,
                        license_spdx = ?, authors_json = ?, keywords_json = ?, release_date = ?,
                        funding_statement = ?, conflict_statement = ?, ai_use_statement = ?,
                        data_availability_statement = ?, updated_at = ?
                    WHERE project_id = ?
                    """,
                    values[2:-2] + (now, project_id),
                )
                entity_id = existing["id"]
                event = "release_profile_updated"
            _audit(conn, project_id, event, {"id": entity_id, "software_version": values[4]})
        return self.get_entity("release-profile", entity_id)

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        if entity_type not in REAL_PILOT_ENTITY_ALIASES:
            raise RealPilotError(f"Unknown v0.5 entity type: {entity_type}")
        table = REAL_PILOT_ENTITY_ALIASES[entity_type]
        with db.connect(self.database) as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            raise KeyError(f"v0.5 entity not found: {entity_id}")
        return self._decode(entity_type, dict(row))

    def list_entities(self, project_id: str, entity_type: str) -> list[dict[str, Any]]:
        if entity_type not in REAL_PILOT_ENTITY_ALIASES:
            raise RealPilotError(f"Unknown v0.5 entity type: {entity_type}")
        table = REAL_PILOT_ENTITY_ALIASES[entity_type]
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            order = "updated_at, id" if entity_type in {"enrollment", "release-profile"} else "created_at, id"
            rows = conn.execute(f"SELECT * FROM {table} WHERE project_id = ? ORDER BY {order}", (project_id,)).fetchall()
        return [self._decode(entity_type, dict(row)) for row in rows]

    @staticmethod
    def _decode(entity_type: str, item: dict[str, Any]) -> dict[str, Any]:
        json_fields = {
            "import-batch": ("mapping_json", "rejected_rows_json"),
            "enrollment": ("data_use_scope_json",),
            "quality-run": ("checks_json", "issues_json"),
            "analysis-run": ("results_json",),
            "release-profile": ("authors_json", "keywords_json"),
        }.get(entity_type, ())
        for field in json_fields:
            item[field.removesuffix("_json")] = db.loads(item.pop(field))
        if entity_type == "import-batch":
            # Surface the import warnings at the top level so that a batch read
            # back later has the same shape as the value returned by
            # import_participants_csv. A record written by hand or by an older
            # release may hold something other than an object here, so the
            # lookup must not assume a mapping.
            mapping = item.get("mapping")
            mapping = mapping if isinstance(mapping, dict) else {}
            warnings = mapping.get("warnings")
            dropped = mapping.get("dropped_columns")
            item["warnings"] = list(warnings) if isinstance(warnings, list) else []
            item["dropped_columns"] = list(dropped) if isinstance(dropped, list) else []
        if "passed" in item:
            item["passed"] = bool(item["passed"])
        return item

    def export_project_entities(self, project_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            table: self.list_entities(project_id, entity_type)
            for entity_type, table in REAL_PILOT_ENTITY_ALIASES.items()
        }

    def quality_check(self, project_id: str, *, run_label: str = "pre-analysis", report_ref: str = "") -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        checks: dict[str, bool] = {}

        def issue(code: str, severity: str, message: str, entity_type: str = "", entity_id: str = "") -> None:
            issues.append({
                "code": code, "severity": severity, "message": message,
                "entity_type": entity_type, "entity_id": entity_id,
            })

        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            studies = [dict(row) for row in conn.execute("SELECT * FROM pilot_studies WHERE project_id = ?", (project_id,))]
            participants = [dict(row) for row in conn.execute("SELECT * FROM pilot_participants WHERE project_id = ?", (project_id,))]
            enrollments = [dict(row) for row in conn.execute("SELECT * FROM participant_enrollments WHERE project_id = ?", (project_id,))]
            sessions = [dict(row) for row in conn.execute("SELECT * FROM pilot_sessions WHERE project_id = ?", (project_id,))]
            tasks = [dict(row) for row in conn.execute("SELECT * FROM pilot_tasks WHERE project_id = ?", (project_id,))]
            attempts = [dict(row) for row in conn.execute("SELECT * FROM pilot_task_attempts WHERE project_id = ?", (project_id,))]
            installs = [dict(row) for row in conn.execute("SELECT * FROM installation_records WHERE project_id = ?", (project_id,))]
            sus = [dict(row) for row in conn.execute("SELECT * FROM sus_responses WHERE project_id = ?", (project_id,))]
            consent_docs = [dict(row) for row in conn.execute("SELECT * FROM consent_documents WHERE project_id = ?", (project_id,))]

        checks["single_protocol"] = len(studies) == 1
        if len(studies) != 1:
            issue("PROTOCOL_COUNT", "blocking", "Exactly one pilot study protocol is required.", "pilot_study")
        study = studies[0] if studies else None
        checks["ethics_resolved"] = bool(study) and study["ethics_status"] in {"approved", "exempt", "not_required"}
        if not checks["ethics_resolved"]:
            issue("ETHICS_UNRESOLVED", "blocking", "Ethics status must be approved, exempt, or not_required.", "pilot_study", study["id"] if study else "")

        enrollment_by_participant = {row["participant_id"]: row for row in enrollments}
        doc_ids = {row["id"] for row in consent_docs}
        active_participants = [row for row in participants if row["consent_status"] != "withdrawn"]
        checks["all_participants_enrolled"] = all(row["id"] in enrollment_by_participant for row in participants)
        for participant in participants:
            enrollment = enrollment_by_participant.get(participant["id"])
            if enrollment is None:
                issue("MISSING_ENROLLMENT", "blocking", "Participant has no v0.5 enrollment record.", "participant", participant["id"])
                continue
            demographics = db.loads(participant["demographics_json"])
            found = _scan_identifier_keys(demographics)
            if found:
                issue("DIRECT_IDENTIFIER_KEY", "blocking", "Participant demographics contain forbidden direct-identifier keys: " + ", ".join(found), "participant", participant["id"])
            if participant["consent_status"] == "consented":
                if not enrollment["consent_document_id"] or enrollment["consent_document_id"] not in doc_ids:
                    issue("CONSENT_DOCUMENT_MISSING", "blocking", "Consented participant is not linked to a registered consent document.", "participant", participant["id"])
                if not enrollment["consented_at"]:
                    issue("CONSENT_TIMESTAMP_MISSING", "blocking", "Consented participant lacks consented_at.", "participant", participant["id"])
            if enrollment["eligibility_status"] != "eligible" and any(s["participant_id"] == participant["id"] for s in sessions):
                issue("INELIGIBLE_SESSION", "blocking", "A non-eligible participant has a recorded session.", "participant", participant["id"])

        required_tasks = {row["id"] for row in tasks if row["required"]}
        attempts_by_session: dict[str, set[str]] = {}
        for attempt in attempts:
            attempts_by_session.setdefault(attempt["session_id"], set()).add(attempt["task_id"])
        installs_by_session = {row["session_id"] for row in installs}
        sus_by_session = {row["session_id"] for row in sus}
        participant_rows = {row["id"]: row for row in participants}
        for session in sessions:
            if session["session_status"] == "completed":
                if not session["started_at"] or not session["ended_at"]:
                    issue("SESSION_TIME_MISSING", "blocking", "Completed session lacks start or end time.", "session", session["id"])
                missing_tasks = sorted(required_tasks - attempts_by_session.get(session["id"], set()))
                if missing_tasks:
                    issue("REQUIRED_TASK_MISSING", "blocking", f"Completed session lacks {len(missing_tasks)} required task attempts.", "session", session["id"])
                if session["condition_name"] == "heritagegate" and session["id"] not in installs_by_session:
                    issue("INSTALLATION_MISSING", "blocking", "Completed HeritageGate session lacks an installation record.", "session", session["id"])
                if session["condition_name"] == "heritagegate" and session["id"] not in sus_by_session:
                    issue("SUS_MISSING", "warning", "Completed HeritageGate session lacks a SUS response.", "session", session["id"])
            participant = participant_rows.get(session["participant_id"])
            enrollment = enrollment_by_participant.get(session["participant_id"])
            if participant and participant["consent_status"] == "withdrawn" and enrollment and enrollment["withdrawn_at"] and session["started_at"]:
                try:
                    if datetime.fromisoformat(session["started_at"].replace("Z", "+00:00")) > datetime.fromisoformat(enrollment["withdrawn_at"].replace("Z", "+00:00")):
                        issue("POST_WITHDRAWAL_SESSION", "blocking", "Session starts after recorded withdrawal.", "session", session["id"])
                except ValueError:
                    issue("INVALID_WITHDRAWAL_TIME", "blocking", "Withdrawal or session time cannot be parsed.", "session", session["id"])

        if study and study["study_design"] == "crossover":
            completed_conditions: dict[str, set[str]] = {}
            for session in sessions:
                if session["session_status"] == "completed":
                    completed_conditions.setdefault(session["participant_id"], set()).add(session["condition_name"])
            for participant in active_participants:
                if completed_conditions.get(participant["id"], set()) != {"heritagegate", "baseline"}:
                    issue("CROSSOVER_INCOMPLETE", "blocking", "Crossover participant lacks one completed condition.", "participant", participant["id"])

        planned = int(study["planned_sample_size"]) if study else 0
        completed_participants = len({s["participant_id"] for s in sessions if s["session_status"] == "completed"})
        if planned and completed_participants < planned:
            issue("SAMPLE_BELOW_PLAN", "warning", f"Completed participant count {completed_participants} is below planned sample {planned}.", "pilot_study", study["id"])

        blocking = sum(1 for row in issues if row["severity"] == "blocking")
        checks.update({
            "no_direct_identifiers": not any(row["code"] == "DIRECT_IDENTIFIER_KEY" for row in issues),
            "consent_links_complete": not any(row["code"] in {"CONSENT_DOCUMENT_MISSING", "CONSENT_TIMESTAMP_MISSING"} for row in issues),
            "required_task_coverage": not any(row["code"] == "REQUIRED_TASK_MISSING" for row in issues),
            "installation_coverage": not any(row["code"] == "INSTALLATION_MISSING" for row in issues),
            "no_post_withdrawal_sessions": not any(row["code"] == "POST_WITHDRAWAL_SESSION" for row in issues),
            "design_complete": not any(row["code"] == "CROSSOVER_INCOMPLETE" for row in issues),
        })
        entity_id = _new_id("quality")
        now = utc_now()
        passed = blocking == 0
        with db.connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO data_quality_runs(
                    id, project_id, run_label, checks_json, issues_json,
                    issue_count, blocking_issue_count, passed, report_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_id, project_id, run_label, db.dumps(checks), db.dumps(issues), len(issues), blocking, int(passed), report_ref, now),
            )
            _audit(conn, project_id, "data_quality_run_completed", {
                "id": entity_id, "passed": passed, "issue_count": len(issues), "blocking_issue_count": blocking
            })
        return self.get_entity("quality-run", entity_id)

    @staticmethod
    def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float | None]:
        if total <= 0:
            return {"estimate_pct": None, "lower_pct": None, "upper_pct": None}
        p = successes / total
        denominator = 1 + z * z / total
        centre = (p + z * z / (2 * total)) / denominator
        margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
        return {
            "estimate_pct": round(100 * p, 3),
            "lower_pct": round(100 * max(0.0, centre - margin), 3),
            "upper_pct": round(100 * min(1.0, centre + margin), 3),
        }

    @staticmethod
    def _bootstrap_mean(values: list[float], *, seed: int, iterations: int = 2000) -> dict[str, float | None]:
        if not values:
            return {"mean": None, "lower": None, "upper": None}
        if len(values) == 1:
            value = round(values[0], 3)
            return {"mean": value, "lower": value, "upper": value}
        rng = random.Random(seed)
        n = len(values)
        estimates = []
        for _ in range(iterations):
            sample = [values[rng.randrange(n)] for _ in range(n)]
            estimates.append(statistics.mean(sample))
        estimates.sort()
        lower = estimates[int(0.025 * (iterations - 1))]
        upper = estimates[int(0.975 * (iterations - 1))]
        return {
            "mean": round(statistics.mean(values), 3),
            "lower": round(lower, 3),
            "upper": round(upper, 3),
        }

    def analysis_results(self, project_id: str, *, seed: int = 20260729) -> dict[str, Any]:
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            sessions = [dict(row) for row in conn.execute("SELECT * FROM pilot_sessions WHERE project_id = ?", (project_id,))]
            attempts = [dict(row) for row in conn.execute("SELECT * FROM pilot_task_attempts WHERE project_id = ?", (project_id,))]
            installs = [dict(row) for row in conn.execute("SELECT * FROM installation_records WHERE project_id = ?", (project_id,))]
            sus = [dict(row) for row in conn.execute("SELECT * FROM sus_responses WHERE project_id = ?", (project_id,))]
            participants = [dict(row) for row in conn.execute("SELECT * FROM pilot_participants WHERE project_id = ?", (project_id,))]
            tasks = [dict(row) for row in conn.execute("SELECT * FROM pilot_tasks WHERE project_id = ?", (project_id,))]
            studies = [dict(row) for row in conn.execute("SELECT * FROM pilot_studies WHERE project_id = ?", (project_id,))]
            benchmarks = [dict(row) for row in conn.execute("SELECT * FROM workflow_benchmarks WHERE project_id = ?", (project_id,))]
        session_map = {row["id"]: row for row in sessions}
        results: dict[str, Any] = {
            "analysis_version": self.ANALYSIS_VERSION,
            "random_seed": seed,
            "project_id": project_id,
            "protocol": {
                "study_design": studies[0]["study_design"] if studies else None,
                "planned_sample_size": studies[0]["planned_sample_size"] if studies else None,
            },
            "sample": {
                "participants": len(participants),
                "completed_participants": len({row["participant_id"] for row in sessions if row["session_status"] == "completed"}),
                "tasks": len(tasks),
                "sessions": len(sessions),
            },
        }
        results["installation"] = {
            "records": len(installs),
            "success_interval": self._wilson(sum(int(row["success"]) for row in installs), len(installs)),
            "duration_seconds": self._bootstrap_mean([float(row["duration_seconds"]) for row in installs], seed=seed + 1),
            "median_seconds": round(statistics.median([float(row["duration_seconds"]) for row in installs]), 3) if installs else None,
        }
        condition: dict[str, Any] = {}
        for index, name in enumerate(("heritagegate", "baseline")):
            session_ids = {row["id"] for row in sessions if row["condition_name"] == name}
            rows = [row for row in attempts if row["session_id"] in session_ids]
            condition[name] = {
                "attempts": len(rows),
                "completion_interval": self._wilson(sum(int(row["success"]) for row in rows), len(rows)),
                "duration_seconds": self._bootstrap_mean([float(row["duration_seconds"]) for row in rows], seed=seed + 10 + index),
                "median_seconds": round(statistics.median([float(row["duration_seconds"]) for row in rows]), 3) if rows else None,
                "mean_errors": round(statistics.mean([float(row["error_count"]) for row in rows]), 3) if rows else None,
                "mean_assistance": round(statistics.mean([float(row["assistance_count"]) for row in rows]), 3) if rows else None,
            }
        results["conditions"] = condition
        sus_scores = [float(row["sus_score"]) for row in sus]
        results["sus"] = {
            "responses": len(sus_scores),
            "score": self._bootstrap_mean(sus_scores, seed=seed + 20),
            "median": round(statistics.median(sus_scores), 3) if sus_scores else None,
            "minimum": round(min(sus_scores), 3) if sus_scores else None,
            "maximum": round(max(sus_scores), 3) if sus_scores else None,
        }

        participant_condition_times: dict[str, dict[str, list[float]]] = {}
        participant_condition_success: dict[str, dict[str, list[int]]] = {}
        for attempt in attempts:
            session = session_map.get(attempt["session_id"])
            if not session:
                continue
            participant_id = session["participant_id"]
            name = session["condition_name"]
            participant_condition_times.setdefault(participant_id, {}).setdefault(name, []).append(float(attempt["duration_seconds"]))
            participant_condition_success.setdefault(participant_id, {}).setdefault(name, []).append(int(attempt["success"]))
        paired_time_differences: list[float] = []
        paired_completion_differences: list[float] = []
        for participant_id, values in participant_condition_times.items():
            if {"heritagegate", "baseline"}.issubset(values):
                paired_time_differences.append(statistics.mean(values["baseline"]) - statistics.mean(values["heritagegate"]))
                success = participant_condition_success[participant_id]
                paired_completion_differences.append(
                    100 * (statistics.mean(success["heritagegate"]) - statistics.mean(success["baseline"]))
                )
        results["paired_comparison"] = {
            "pairs": len(paired_time_differences),
            "baseline_minus_heritagegate_seconds": self._bootstrap_mean(paired_time_differences, seed=seed + 30),
            "heritagegate_minus_baseline_completion_points": self._bootstrap_mean(paired_completion_differences, seed=seed + 31),
        }
        time_reductions = [
            100 * (float(row["baseline_seconds"]) - float(row["heritagegate_seconds"])) / float(row["baseline_seconds"])
            for row in benchmarks if float(row["baseline_seconds"]) > 0
        ]
        results["workflow_benchmarks"] = {
            "records": len(benchmarks),
            "time_reduction_pct": self._bootstrap_mean(time_reductions, seed=seed + 40),
        }
        canonical = json.dumps({
            "sessions": sessions, "attempts": attempts, "installs": installs,
            "sus": sus, "participants": participants, "tasks": tasks,
            "studies": studies, "benchmarks": benchmarks,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        results["input_sha256"] = _sha256_text(canonical)
        results["interpretation_limit"] = (
            "Intervals are descriptive resampling or binomial intervals. They do not establish causality; "
            "claims depend on study design, allocation, missingness, and sample adequacy."
        )
        return results

    def write_statistical_report(
        self, project_id: str, output_directory: str | Path, *, seed: int = 20260729
    ) -> dict[str, Any]:
        destination = Path(output_directory).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        quality = self.quality_check(project_id, run_label="pre-statistical-report", report_ref=str(destination))
        results = self.analysis_results(project_id, seed=seed)
        result_path = destination / "analysis_results.json"
        result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        # The quality dictionary carries a per-run identifier and timestamp.
        # Writing those into a checksummed artefact makes the artefact differ on
        # every run, so `sha256sum -c SHA256SUMS.txt` reports a failure even
        # when the analysis is perfectly reproducible. The reproducibility-
        # relevant fact is the quality *state*, not which row recorded it, so
        # the run-scoped fields move to analysis_run_context.json, which is
        # deliberately excluded from the checksum file.
        quality_state = {k: v for k, v in quality.items() if k not in {"id", "created_at", "report_ref"}}
        quality_state_sha256 = _sha256_text(
            json.dumps(quality_state, ensure_ascii=False, sort_keys=True)
        )
        quality_path = destination / "data_quality_report.json"
        quality_path.write_text(
            json.dumps(quality_state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        rows: list[dict[str, Any]] = []
        for condition, values in results["conditions"].items():
            rows.append({
                "section": "condition", "group": condition,
                "n": values["attempts"],
                "estimate": values["completion_interval"]["estimate_pct"],
                "lower": values["completion_interval"]["lower_pct"],
                "upper": values["completion_interval"]["upper_pct"],
                "unit": "completion_percent",
            })
            rows.append({
                "section": "condition", "group": condition,
                "n": values["attempts"],
                "estimate": values["duration_seconds"]["mean"],
                "lower": values["duration_seconds"]["lower"],
                "upper": values["duration_seconds"]["upper"],
                "unit": "seconds",
            })
        rows.append({
            "section": "sus", "group": "heritagegate", "n": results["sus"]["responses"],
            "estimate": results["sus"]["score"]["mean"], "lower": results["sus"]["score"]["lower"],
            "upper": results["sus"]["score"]["upper"], "unit": "score_0_100",
        })
        table_path = destination / "analysis_table.csv"
        with table_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["section", "group", "n", "estimate", "lower", "upper", "unit"])
            writer.writeheader(); writer.writerows(rows)
        report = self._analysis_markdown(results, quality, quality_state_sha256)
        report_path = destination / "analysis_report.md"
        report_path.write_text(report, encoding="utf-8")
        input_manifest = {
            "project_id": project_id, "analysis_version": self.ANALYSIS_VERSION,
            "random_seed": seed, "input_sha256": results["input_sha256"],
            "quality_state_sha256": quality_state_sha256,
            "quality_passed": quality["passed"],
            "blocking_issue_count": quality["blocking_issue_count"],
        }
        (destination / "analysis_input_manifest.json").write_text(
            json.dumps(input_manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        entity_id = _new_id("analysis")
        now = utc_now()
        # Run-scoped provenance is retained, but outside the checksum set so
        # that the reproducible artefacts stay byte-identical across runs.
        (destination / RUN_CONTEXT_FILENAME).write_text(
            json.dumps({
                "analysis_run_id": entity_id,
                "quality_run_id": quality["id"],
                "generated_at": now,
                "output_directory": str(destination),
                "note": (
                    "Run-scoped identifiers. Excluded from SHA256SUMS.txt by design: "
                    "these change on every run, while the checksummed artefacts do not."
                ),
            }, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        checksums = []
        for path in sorted(
            p for p in destination.iterdir()
            if p.is_file() and p.name not in {"SHA256SUMS.txt", RUN_CONTEXT_FILENAME}
        ):
            checksums.append(f"{_sha256_bytes(path.read_bytes())}  {path.name}")
        (destination / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
        with db.connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO analysis_runs(
                    id, project_id, analysis_version, random_seed,
                    input_sha256, results_json, report_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_id, project_id, self.ANALYSIS_VERSION, seed, results["input_sha256"], db.dumps(results), str(report_path), now),
            )
            _audit(conn, project_id, "statistical_report_generated", {
                "id": entity_id, "input_sha256": results["input_sha256"], "quality_passed": quality["passed"]
            })
        metadata = self.get_entity("analysis-run", entity_id)
        metadata["output_directory"] = str(destination)
        metadata["files"] = sorted(path.name for path in destination.iterdir() if path.is_file())
        return metadata

    @staticmethod
    def _analysis_markdown(
        results: Mapping[str, Any], quality: Mapping[str, Any], quality_state_sha256: str = ""
    ) -> str:
        hg = results["conditions"]["heritagegate"]
        base = results["conditions"]["baseline"]
        paired = results["paired_comparison"]
        return f"""# HeritageGate reproducible pilot analysis

## Reproducibility metadata

- Analysis version: `{results['analysis_version']}`
- Random seed: `{results['random_seed']}`
- Input SHA-256: `{results['input_sha256']}`
- Data-quality state: `{quality_state_sha256[:16]}`
- Blocking issues: **{quality['blocking_issue_count']}**

## Sample

The database contains **{results['sample']['participants']}** de-identified participants, **{results['sample']['completed_participants']}** participants with at least one completed session, **{results['sample']['sessions']}** sessions, and **{results['sample']['tasks']}** defined tasks.

## Installation feasibility

Installation succeeded in **{results['installation']['success_interval']['estimate_pct']}%** of recorded attempts (Wilson 95% interval: **{results['installation']['success_interval']['lower_pct']}%–{results['installation']['success_interval']['upper_pct']}%**). Mean installation time was **{results['installation']['duration_seconds']['mean']} s** (bootstrap 95% interval: **{results['installation']['duration_seconds']['lower']}–{results['installation']['duration_seconds']['upper']} s**).

## Task performance

HeritageGate task completion was **{hg['completion_interval']['estimate_pct']}%** (Wilson 95% interval: **{hg['completion_interval']['lower_pct']}%–{hg['completion_interval']['upper_pct']}%**), compared with **{base['completion_interval']['estimate_pct']}%** under the baseline workflow (Wilson 95% interval: **{base['completion_interval']['lower_pct']}%–{base['completion_interval']['upper_pct']}%**).

Mean task time was **{hg['duration_seconds']['mean']} s** with HeritageGate and **{base['duration_seconds']['mean']} s** under the baseline. For **{paired['pairs']}** paired participants, the mean baseline-minus-HeritageGate time difference was **{paired['baseline_minus_heritagegate_seconds']['mean']} s** (bootstrap 95% interval: **{paired['baseline_minus_heritagegate_seconds']['lower']}–{paired['baseline_minus_heritagegate_seconds']['upper']} s**).

## Usability

The mean SUS score was **{results['sus']['score']['mean']}** from **{results['sus']['responses']}** responses (bootstrap 95% interval: **{results['sus']['score']['lower']}–{results['sus']['score']['upper']}**).

## Interpretation boundary

{results['interpretation_limit']} The report must not be used to imply that consent, ethics approval, participant identity, or external evidence has been independently verified by HeritageGate.
"""

    def latest_quality_run(self, project_id: str) -> dict[str, Any] | None:
        rows = self.list_entities(project_id, "quality-run")
        return rows[-1] if rows else None

    def latest_analysis_run(self, project_id: str) -> dict[str, Any] | None:
        rows = self.list_entities(project_id, "analysis-run")
        return rows[-1] if rows else None

    def get_release_profile(self, project_id: str) -> dict[str, Any] | None:
        rows = self.list_entities(project_id, "release-profile")
        return rows[-1] if rows else None

    def release_readiness(self, project_id: str) -> dict[str, Any]:
        profile = self.get_release_profile(project_id)
        quality = self.latest_quality_run(project_id)
        analysis = self.latest_analysis_run(project_id)
        with db.connect(self.database) as conn:
            self._require_project(conn, project_id)
            participants = [dict(row) for row in conn.execute("SELECT * FROM pilot_participants WHERE project_id = ?", (project_id,))]
            enrollments = [dict(row) for row in conn.execute("SELECT * FROM participant_enrollments WHERE project_id = ?", (project_id,))]
        synthetic = False
        for participant in participants:
            demographics = db.loads(participant["demographics_json"])
            synthetic = synthetic or bool(demographics.get("synthetic"))
        checks = {
            "release_profile_recorded": profile is not None,
            "software_version_matches_package": bool(profile) and profile["software_version"] == __version__,
            "validated_real_pilot": bool(profile) and profile["evidence_status"] == "validated_real_pilot",
            "quality_passed": bool(quality) and quality["passed"],
            "statistical_report_generated": analysis is not None,
            "no_synthetic_participants": bool(participants) and not synthetic,
            "all_participants_enrolled": bool(participants) and len(enrollments) == len(participants),
            "repository_url_recorded": bool(profile) and bool(profile["repository_url"]),
            "archive_url_recorded": bool(profile) and bool(profile["archive_url"]),
            "software_doi_recorded": bool(profile) and bool(profile["software_doi"]),
            "executable_url_recorded": bool(profile) and bool(profile["executable_url"]),
            "documentation_url_recorded": bool(profile) and bool(profile["documentation_url"]),
            "support_email_recorded": bool(profile) and bool(profile["support_email"]),
            "release_candidate_or_released": bool(profile) and profile["release_status"] in {"candidate", "released"},
        }
        return {
            "schema_version": db.SCHEMA_VERSION,
            "project_id": project_id,
            "checks": checks,
            "passed": sum(checks.values()),
            "total": len(checks),
            "ready": all(checks.values()),
            "profile": profile,
            "latest_quality_run_id": quality["id"] if quality else None,
            "latest_analysis_run_id": analysis["id"] if analysis else None,
            "notice": "Readiness is an automated completeness check, not editorial approval or external verification.",
        }
