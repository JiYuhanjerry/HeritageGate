# Pilot study module

HeritageGate v0.4.0 adds eight normalized pilot-study record classes. The module is designed to support descriptive feasibility and usability evidence for a SoftwareX software paper while keeping the Gate 0–7 governance workflow intact.

## Record classes

| Record class | Purpose |
|---|---|
| `pilot_studies` | Stores protocol version, design, ethics status, planned sample, outcomes, and eligibility criteria. |
| `pilot_participants` | Stores de-identified participant codes, role, experience, consent status, and non-identifying descriptors. |
| `pilot_tasks` | Defines standardized tasks and expected outcomes. |
| `pilot_sessions` | Links participants to HeritageGate or baseline conditions and records environment and status. |
| `installation_records` | Records timed installation attempts, method, software version, errors, and evidence reference. |
| `pilot_task_attempts` | Records task duration, success, completion state, errors, assistance, and evidence reference. |
| `sus_responses` | Stores ten SUS responses and the automatically computed 0–100 score. |
| `workflow_benchmarks` | Stores direct HeritageGate-versus-baseline time and error comparisons. |

## Built-in validation

The module rejects:

- consented participants without a consent reference;
- new sessions for withdrawn participants;
- completed sessions without start and end timestamps;
- installation records linked to baseline sessions;
- task attempts with negative duration;
- successful task attempts not marked completed;
- SUS responses that do not contain exactly ten integers from 1 to 5;
- workflow benchmarks with a zero baseline duration.

## Metrics

`pilot-summary` calculates installation success, installation duration, task completion, task duration, error and assistance rates, SUS distribution, and workflow time/error reduction. All results are descriptive. HeritageGate does not perform inferential tests or causal identification.

## Privacy

Use participant codes rather than names. Do not place consent forms, email addresses, phone numbers, or sensitive demographic information in demonstration databases. The database is local but is not encrypted by HeritageGate v0.4.0.
