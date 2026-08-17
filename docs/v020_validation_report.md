# v0.2.0 validation report

Validation performed on 2026-07-29.

## Source test suite

Command:

```text
PYTHONPATH=src python -m unittest discover -s tests -v
```

Result:

```text
Ran 16 tests
OK
```

Coverage includes:

- original Gate 0–7 transition rules;
- rollback and failed-review feedback;
- rights-holder and authorization integrity;
- bearer/community annotation requirements;
- model-to-element provenance links;
- Gate 5 role-specific approvals;
- bounded market-test scores;
- cumulative revenue-share controls;
- non-destructive v0.1 database upgrade;
- complete structured Gate 0–7 demonstration.

## Wheel validation

The standard-library builder produced:

```text
heritagegate-0.2.0-py3-none-any.whl
```

The wheel was installed into a clean Python virtual environment without network
access or third-party runtime dependencies. The installed command reported
version `0.2.0` and completed the structured demo at Gate 7.

## Structured demonstration output

- schema version: `0.2.0`
- project status: `completed`
- current gate: `7`
- gate records: `8`
- rights holders: `3`
- authorization records: `1`
- cultural-element cards: `2`
- model runs: `1`
- expert reviews: `3`
- market tests: `1`
- revenue distributions: `1`

This validation does not replace independent testing on all claimed operating
systems or testing with ethically authorized real-world heritage data.
