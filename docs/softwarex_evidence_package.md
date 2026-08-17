# SoftwareX evidence package

The `export-softwarex-evidence` command builds a portable ZIP intended to support the *Illustrative examples* and *Impact* sections of a SoftwareX manuscript.

## Package contents

- Complete project manifest in JSON.
- Pilot summary in JSON.
- Raw pilot tables in UTF-8 CSV format.
- SoftwareX evidence-readiness checklist.
- Descriptive evidence report in Markdown.
- Candidate manuscript results sentences in Markdown.
- Vector SVG figures for installation success, task completion, task duration, SUS, and workflow benchmark time.
- Package metadata and SHA-256 checksums.

## Interpretation limits

The software verifies data types, relationships, timing arithmetic, SUS scoring, aggregation, and file integrity. It cannot verify whether:

- the participants existed;
- ethics approval or exemption was valid;
- consent was properly obtained;
- evidence references point to authentic records;
- baseline and HeritageGate conditions were comparable;
- the pilot design supports causal or inferential claims.

Synthetic records must never be described as empirical evidence.
