# Real-pilot implementation

HeritageGate v0.5 separates local participant recruitment operations from the
public research-software release. The module is designed to reduce accidental
retention of direct identifiers; it is not an identity-management or clinical
research system.

## Consent-document metadata

`consent_documents` stores the document title, version, language, ethics
reference, effective date, withdrawal contact, retention policy, local body
reference, and SHA-256 digest. The file itself is not stored in SQLite and is not
included in public release packages.

## Participant import

The importer accepts a CSV with a local `source_id`. It computes:

- `identity_token_hash = SHA256(project_id | source_id)`;
- a generated participant code derived from the hash prefix;
- a source-row SHA-256 for change detection.

The original `source_id` is not inserted into SQLite. Common direct-identifier
headers are refused before any row is processed. Direct-identifier keys inside
`demographics_json` are also refused.

This mechanism is pseudonymization, not anonymization in the legal sense. A
study team that retains the source CSV can still reconnect the record to a
person. Store the source CSV outside HeritageGate under an approved access and
retention policy.

## Enrollment and withdrawal

`participant_enrollments` links the de-identified participant to a consent
document, eligibility status, consent time, withdrawal time, data-use scope,
and import provenance. A participant marked `withdrawn` cannot be assigned a
new pilot session by the pilot manager. The quality checker also flags sessions
whose start time occurs after withdrawal.

## Data-quality checks

The checker reports blocking issues and warnings. Blocking issues include:

- missing or unresolved protocol/ethics metadata;
- participant records without v0.5 enrollment;
- consented participants without document or consent timestamp;
- forbidden direct-identifier keys in demographics;
- sessions for ineligible participants;
- completed sessions without required task attempts;
- HeritageGate sessions without installation records;
- post-withdrawal sessions;
- incomplete crossover conditions.

A planned sample shortfall and missing SUS response are warnings. Projects may
have legitimate reasons for these conditions, but they must be discussed and
cannot be silently omitted.

## Security boundary

HeritageGate uses local SQLite and a local browser server. Version 0.5 does not
provide authentication, encryption at rest, role-based access control, secure
identity vaults, remote consent signing, or electronic regulatory compliance.
Restricted participant and heritage records must remain in an appropriately
secured environment.
