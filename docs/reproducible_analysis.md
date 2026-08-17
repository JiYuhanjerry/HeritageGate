# Reproducible analysis

The `analyze-pilot` command produces a deterministic report from the active
SQLite database.

## Outputs

- `analysis_results.json`: nested machine-readable results;
- `analysis_report.md`: manuscript-oriented descriptive report;
- `analysis_table.csv`: compact estimates and intervals;
- `analysis_input_manifest.json`: analysis version, seed, input digest, and
  data-quality run;
- `data_quality_report.json`: checks and issues used at report time;
- `SHA256SUMS.txt`: file checksums.

## Statistical calculations

- Installation and task-completion proportions use Wilson 95% intervals.
- Mean installation time, task duration, SUS, workflow reduction, and paired
  differences use percentile bootstrap intervals with a recorded random seed.
- Crossover comparisons use a participant-level mean within each condition
  before calculating the paired difference.

## Interpretation

These calculations are descriptive. A confidence interval produced by the
software does not establish causal identification, random assignment, absence
of missing-data bias, measurement validity, or adequate power. The study design,
allocation sequence, exclusions, missing observations, protocol deviations,
and sample size must be reported separately.

## Reproducibility

The analysis input SHA-256 is computed from a canonical JSON representation of
the protocol, participants, tasks, sessions, installation records, task
attempts, SUS responses, and workflow benchmarks. Re-running with the same
records, code version, and random seed should reproduce the same output.
