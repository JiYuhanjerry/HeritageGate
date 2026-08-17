# v0.5 real-pilot templates

This directory ships the two templates referenced by the root README.

## `participant_import_template.csv`

Format reference for `heritagegate import-participants`. The single data row is
synthetic and exists only to document the expected columns and value formats.
Replace it with real de-identified rows before importing.

Required columns: `source_id`, `participant_role`, `experience_level`,
`consent_status`. Optional columns: `consented_at`, `eligibility_status`,
`demographics_json`, `data_use_scope_json`, `notes`.

Accepted values:

- `participant_role`: `researcher`, `bearer`, `cultural_expert`, `designer`,
  `developer`, `student`, `other`
- `experience_level`: `novice`, `intermediate`, `advanced`
- `consent_status`: `consented`, `exempt`, `withdrawn` (rows marked
  `consented` require `--consent-document-id` and an ISO-8601 `consented_at`)
- `eligibility_status`: `eligible`, `ineligible`, `pending`

Do not add names, email addresses, phone numbers, addresses, birth dates,
identity-document numbers, or messaging identifiers. The importer refuses
direct-identifier column headers and direct-identifier keys inside
`demographics_json`, including common Chinese-language variants.

## `release_profile_template.json`

Starting point for `heritagegate configure-release`. Fields marked
`[TO BE COMPLETED: ...]` must be replaced before the profile is used for a
real submission. `software_version` must match the installed package version;
`release_status` must be one of `draft`, `candidate`, `released`; and
`evidence_status` must be one of `synthetic`, `real_pilot`,
`validated_real_pilot`. A configured profile does not by itself satisfy the
release-readiness checks: repository, archive, DOI, evidence status, and all
statements still require human verification.
