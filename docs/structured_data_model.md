# HeritageGate v0.2.0 structured data model

Version 0.2.0 converts the principal governance and evaluation records from
anonymous gate payloads into independent, queryable entities. Generic gate
records remain as immutable transition evidence and for backward compatibility.

## Core relationships

```text
projects
  ├─ rights_holders
  │    ├─ authorization_parties ─ authorization_records
  │    ├─ element_annotators ─ cultural_element_cards
  │    ├─ expert_reviews ─ model_runs
  │    └─ revenue_distributions ─ authorization_records
  ├─ model_runs ─ model_run_elements ─ cultural_element_cards
  ├─ market_tests ─ model_runs
  ├─ gate_records
  └─ audit_events
```

## Entity definitions

### Rights holder

Represents a bearer, community, cultural authority, institution, designer,
platform, producer, or other actor with a documented basis for participation.
The entity deliberately stores a `contact_ref` rather than requiring personal
contact data in the research database.

### Authorization record

Stores approval status, permitted and prohibited uses, attribution requirements,
revenue terms, validity dates, and evidence reference. The
`authorization_parties` table supports multiple authorizers, beneficiaries, and
representatives without duplicating the authorization itself.

### Cultural-element card

Stores a versioned cultural and technical description for one element, including
meaning, source, attribution, permitted and prohibited uses, technical features,
prohibited combinations, sensitivity level, and status. Annotators are stored in
a separate relation so bearer/community co-annotation can be tested directly.

### Model run

Stores model identity, version, constraint method, parameters, output count,
provenance reference, and run status. `model_run_elements` establishes a direct
many-to-many relationship between each run and the exact approved cultural
cards used as inputs.

### Expert review

Stores a role-specific review of a model run. Gate 5 requires approved evidence
from: (i) a bearer or cultural expert, (ii) a design expert, and (iii) a
production expert. Role-relevant scores are constrained to 1–5.

### Market test

Stores sample size, channel, five 1–5 measures, recommendation, and report
reference. The measures combine cultural-reception indicators with commercial
intention indicators.

### Revenue distribution

Links an approved authorization, a named recipient, a revenue category, a
three-letter currency, a reporting period, gross amount, share percentage,
distributed amount, and evidence reference. Cumulative shares and distributed
amounts cannot exceed 100% and the stated gross amount for the same
authorization/currency/period.

## Structured gate construction

| Gate | Evidence assembled by the software |
|---|---|
| 1 | Approved authorizations and active authorizer parties |
| 3 | Approved cultural cards, documented prohibited combinations, eligible annotators |
| 4 | Latest completed model run, approved source cards, provenance reference |
| 5 | Approved bearer/cultural, design, and production reviews for the completed run |
| 6 | Latest complete market-test record |
| 7 | Current rights map, approved revenue terms, distribution records, governance owner, audit/takedown readiness |

Gates 0 and 2 remain dedicated gate-evidence records in v0.2.0 because a
separate red-line decision entity and captured-dataset entity are scheduled for
a later release.
