"""GitHub/Zenodo metadata and SoftwareX submission-release packages for v0.5."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping

from .engine import HeritageGateEngine
from .exporter import _neutralize_formula


def _slug(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-") or "project"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: _neutralize_formula(v) for k, v in row.items()} for row in rows])


def _author_names(profile: Mapping[str, Any]) -> str:
    return ", ".join(str(author.get("name", "")).strip() for author in profile["authors"])


def _citation_cff(profile: Mapping[str, Any]) -> str:
    authors = []
    for author in profile["authors"]:
        name = str(author.get("name", "")).strip()
        family = str(author.get("family_names", "")).strip()
        given = str(author.get("given_names", "")).strip()
        if not family and not given:
            parts = name.rsplit(" ", 1)
            given, family = (parts[0], parts[1]) if len(parts) == 2 else ("", name)
        lines = ["  - family-names: " + json.dumps(family or name)]
        if given:
            lines.append("    given-names: " + json.dumps(given))
        if author.get("orcid"):
            lines.append("    orcid: " + json.dumps(str(author["orcid"])))
        if author.get("affiliation"):
            lines.append("    affiliation: " + json.dumps(str(author["affiliation"])))
        authors.extend(lines)
    return f'''cff-version: 1.2.0
message: "If you use this software, please cite it using the metadata below."
title: {json.dumps(profile['software_title'])}
version: {json.dumps(profile['software_version'])}
doi: {json.dumps(profile['software_doi'])}
url: {json.dumps(profile['repository_url'])}
repository-code: {json.dumps(profile['repository_url'])}
license: {json.dumps(profile['license_spdx'])}
date-released: {json.dumps(profile['release_date'])}
authors:
{chr(10).join(authors)}
'''


def _codemeta(profile: Mapping[str, Any]) -> dict[str, Any]:
    authors = []
    for author in profile["authors"]:
        authors.append({
            "@type": "Person",
            "name": author.get("name", ""),
            "givenName": author.get("given_names", ""),
            "familyName": author.get("family_names", ""),
            "affiliation": author.get("affiliation", ""),
            "@id": author.get("orcid", ""),
        })
    return {
        "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
        "@type": "SoftwareSourceCode",
        "name": profile["software_title"],
        "version": profile["software_version"],
        "codeRepository": profile["repository_url"],
        "downloadUrl": profile["executable_url"],
        "softwareHelp": profile["documentation_url"],
        "license": profile["license_spdx"],
        "identifier": profile["software_doi"],
        "datePublished": profile["release_date"],
        "author": authors,
        "keywords": profile["keywords"],
        "programmingLanguage": "Python",
        "operatingSystem": ["Windows", "Linux", "macOS"],
        "applicationCategory": "ResearchSoftware",
    }


def _zenodo(profile: Mapping[str, Any]) -> dict[str, Any]:
    creators = []
    for author in profile["authors"]:
        creator = {"name": author.get("name", "")}
        if author.get("orcid"):
            creator["orcid"] = str(author["orcid"]).replace("https://orcid.org/", "")
        if author.get("affiliation"):
            creator["affiliation"] = author["affiliation"]
        creators.append(creator)
    return {
        "title": profile["software_title"],
        "upload_type": "software",
        "description": (
            "HeritageGate is a stage-gated, rights-aware research workflow for "
            "AI-assisted productization of motif-rich intangible cultural heritage."
        ),
        "creators": creators,
        "license": profile["license_spdx"],
        "keywords": profile["keywords"],
        "version": profile["software_version"],
        "access_right": "open",
        "related_identifiers": [
            {"identifier": profile["repository_url"], "relation": "isSupplementTo", "scheme": "url"}
        ] if profile["repository_url"] else [],
    }


def _metadata_tables(profile: Mapping[str, Any]) -> str:
    return f"""# SoftwareX metadata tables

## Code metadata

| Field | Value |
|---|---|
| Current code version | {profile['software_version']} |
| Permanent link to code/repository used for this code version | {profile['repository_url'] or 'TO BE ADDED'} |
| Permanent link to Reproducible Capsule | TO BE ADDED IF AVAILABLE |
| Legal Code License | {profile['license_spdx']} |
| Code versioning system used | git |
| Software code languages, tools and services used | Python 3.10+, SQLite, standard-library HTTP server, GitHub Actions |
| Compilation requirements, operating environments and dependencies | No compilation; Python 3.10+; Windows, Linux, or macOS; no mandatory third-party runtime dependencies |
| Developer documentation/manual | {profile['documentation_url'] or 'TO BE ADDED'} |
| Support email | {profile['support_email'] or 'TO BE ADDED'} |

## Software metadata

| Field | Value |
|---|---|
| Current software version | {profile['software_version']} |
| Permanent link to executables of this version | {profile['executable_url'] or 'TO BE ADDED'} |
| Permanent link to Reproducible Capsule | TO BE ADDED IF AVAILABLE |
| Legal Software License | {profile['license_spdx']} |
| Computing platforms / Operating Systems | Windows, Linux, macOS; local web browser interface |
| Installation requirements and dependencies | Python 3.10+; install from wheel or editable source |
| User manual | {profile['documentation_url'] or 'TO BE ADDED'} |
| Support email | {profile['support_email'] or 'TO BE ADDED'} |
"""


def _highlights() -> str:
    highlights = [
        "Implements an eight-gate rights-aware heritage AI workflow",
        "Links authorization, cultural elements, model runs, and audits",
        "Captures de-identified usability and workflow pilot evidence",
        "Generates reproducible statistics and SoftwareX evidence packages",
        "Runs locally with Python, SQLite, and no mandatory web framework",
    ]
    return "\n".join(f"• {item}" for item in highlights) + "\n"


def _manuscript_draft(project: Mapping[str, Any], profile: Mapping[str, Any], results: Mapping[str, Any], readiness: Mapping[str, Any]) -> str:
    hg = results["conditions"]["heritagegate"]
    base = results["conditions"]["baseline"]
    sus = results["sus"]
    install = results["installation"]
    paired = results["paired_comparison"]
    repository = profile["repository_url"] or "[permanent repository link to be inserted]"
    doi = profile["software_doi"] or "[software DOI to be inserted]"
    return f"""# {profile['manuscript_title']}

**Authors:** {_author_names(profile)}

## Abstract

Researchers and cultural-creative teams working with motif-rich intangible cultural heritage must coordinate cultural authorization, semantic documentation, AI generation, expert review, market testing, and benefit governance, yet these records are commonly fragmented across spreadsheets, documents, and model-specific tools. HeritageGate is an open-source Python application that converts this coordination problem into an eight-gate, evidence-bearing workflow. The software stores normalized rights holders, authorization records, cultural-element cards, model provenance, multi-role expert reviews, market evidence, revenue distributions, and de-identified pilot-study observations in SQLite. A local browser interface supports project inspection, while command-line tools generate research exports, data-quality reports, deterministic statistical summaries, and SoftwareX submission materials. HeritageGate is intended for researchers, heritage bearers, cultural experts, designers, and AI practitioners who require traceable transitions from permission assessment to asset and revenue governance. The release is available at {repository} and archived under {doi}.

**Keywords:** {', '.join(profile['keywords'])}

## 1. Motivation and significance

AI-assisted cultural design can expand the design space available to motif-rich heritage projects, but technical generation is only one step in a larger workflow. Projects must determine whether a motif may be used, identify legitimate authorizers and beneficiaries, record attribution and prohibited uses, preserve cultural meaning during digitization, constrain model use, involve bearers and experts in review, collect cultural-reception evidence, and govern resulting assets and revenues. In practice, these records are often maintained in unrelated documents or not recorded in a form that can be traced across stages.

General project-management tools can record tasks but do not encode the domain-specific dependencies between authorization, cultural annotation, model provenance, expert review, and downstream governance. Model cards and dataset cards improve documentation of technical artifacts but do not themselves implement stage transitions, authorization binding, review rollback, or revenue-governance records. Analysis scripts can summarize a single study but usually lack an independently reusable operational workflow. HeritageGate addresses this gap as a research-software artifact rather than as a static conceptual framework.

The non-trivial contribution is an executable coupling of three rule classes: upstream decisions bind downstream operations; evidence objects produced at one gate become required inputs to later gates; and failed review or audit findings can return a project to an earlier gate with a preserved audit trail. The software also connects workflow execution to de-identified pilot evidence, deterministic data-quality checks, and reproducible descriptive analysis. These capabilities make it possible to study not only whether a workflow completes but how installation feasibility, task completion, errors, assistance, usability, and baseline comparisons vary across users and environments.

## 2. Software description

### 2.1 Software architecture

HeritageGate is implemented in Python 3.10+ and uses SQLite as its persistence layer. The package is organized into a workflow engine, normalized governance-data manager, pilot-study manager, real-pilot operations manager, data-quality and statistical-analysis functions, research exporters, SoftwareX evidence generators, and a dependency-free local HTTP interface. The command-line interface and browser interface use the same validation and persistence rules, avoiding divergent behavior between interactive and scripted use.

The workflow engine maintains the current completed gate and enforces Gate 0 through Gate 7 order. Generic gate records preserve submitted evidence, while normalized tables store rights holders, authorizations, cultural-element cards, model runs, expert reviews, market tests, and revenue distributions. The v0.5 real-pilot layer registers versioned consent-document metadata, imports participant rows through a direct-identifier refusal policy, stores only hashed source tokens and generated participant codes, records withdrawals, runs integrity checks, and creates deterministic reports linked to input hashes and random seeds.

### 2.2 Software functionalities

**Stage-gated workflow.** Projects progress through red-line classification, prior authorization, digital capture, cultural-element modeling, constrained AI generation, bearer and expert validation, market testing, and asset and revenue governance. Gate transitions are rejected when required upstream evidence is absent.

**Rights and cultural provenance.** Authorization parties, permitted and prohibited uses, cultural meanings, source references, attribution text, technical features, model parameters, and review evidence are linked through normalized relations. A generated output can therefore be traced back to its cultural-element cards and authorization context.

**Multi-role review and rollback.** The software distinguishes bearer, cultural, design, production, legal, and other review roles. Review failure can return the project to an earlier gate without deleting the original decision history.

**Real-pilot safeguards.** CSV participant import refuses common direct-identifier columns, hashes local source identifiers, and does not retain the original identifier. Consented participants must be linked to a registered, versioned consent-document record. Withdrawal prevents new sessions and is checked against session timestamps.

**Data-quality and analysis.** Automated checks identify unresolved ethics status, missing enrollments, consent gaps, direct-identifier keys, incomplete crossover sessions, missing required tasks, missing installations, post-withdrawal sessions, and sample shortfalls. Statistical exports use Wilson intervals for binary outcomes and seeded bootstrap intervals for means and paired differences. Each run records an input SHA-256 digest.

**Publication preparation.** HeritageGate generates GitHub release notes, Citation File Format, CodeMeta, Zenodo metadata, SoftwareX code and software metadata tables, highlights, a manuscript draft, aggregate evidence, privacy-exclusion notes, checklists, and checksums.

## 3. Illustrative examples

The v0.5 demonstration creates a synthetic crossover project and exercises the complete evidence pipeline. Synthetic records are explicitly marked and are not valid empirical findings. For an authorized real pilot, a study team first registers the approved or exempt protocol and a versioned consent-document record. A CSV containing local source identifiers, roles, experience levels, consent status, eligibility, and non-identifying demographics is then imported. HeritageGate replaces each source identifier with a deterministic hashed token and generated participant code; the original identifier is not stored.

After installation and task sessions are recorded, the `quality-check` command evaluates consent, enrollment, study-design, task-coverage, and withdrawal rules. The `analyze-pilot` command writes a Markdown report, JSON results, analysis CSV, input manifest, and SHA-256 checksums. In the currently recorded dataset, installation success is {install['success_interval']['estimate_pct']}% (Wilson 95% interval {install['success_interval']['lower_pct']}%–{install['success_interval']['upper_pct']}%). HeritageGate task completion is {hg['completion_interval']['estimate_pct']}%, compared with {base['completion_interval']['estimate_pct']}% for the baseline. Mean SUS is {sus['score']['mean']} from {sus['responses']} responses. For {paired['pairs']} paired participants, the mean baseline-minus-HeritageGate task-time difference is {paired['baseline_minus_heritagegate_seconds']['mean']} s. These values are generated from the active database and require author verification before publication.

A minimal command sequence is:

```text
heritagegate --db pilot.db register-consent PROJECT consent.pdf --title "Pilot consent" --version 1.0 --language en --effective-from 2026-01-01 --withdrawal-contact research@example.org --retention-policy "Retain de-identified data for five years"
heritagegate --db pilot.db import-participants PROJECT participants.csv --consent-document-id CONSENT_ID
heritagegate --db pilot.db quality-check PROJECT
heritagegate --db pilot.db analyze-pilot PROJECT analysis_output
heritagegate --db pilot.db export-submission-release PROJECT submission_release.zip
```

## 4. Impact

HeritageGate changes a fragmented documentation process into a queryable, versioned, and auditable research workflow. Researchers can inspect whether later outputs are supported by prior permission and cultural annotation; bearers and experts can be represented as distinct authority and review roles; developers can trace generated outputs to model versions and cultural elements; and project teams can export aggregate evidence without automatically including participant-level records.

The software is transferable beyond a single cultural tradition because its inputs are structured records rather than hard-coded motifs or private datasets. It can support embroidery, brocade, paper-cutting, decorative print, and related motif-rich traditions, provided that authorizing parties and cultural constraints can be identified. The pilot module can also be reused to evaluate other rights-aware research workflows that need timed tasks, usability measures, baseline comparisons, withdrawal handling, and reproducible evidence packages.

The current automated release-readiness checklist passes {readiness['passed']} of {readiness['total']} conditions. This score is a completeness aid rather than a guarantee of scientific validity or editorial acceptance. Genuine impact claims require independent installation, authorized real-pilot records, and transparent reporting of study design and limitations.

## 5. Conclusions

HeritageGate operationalizes protected productization as an eight-gate software workflow linking cultural permission, semantic documentation, AI provenance, multi-stakeholder review, market evidence, and benefit governance. Version {profile['software_version']} adds real-pilot enrollment safeguards, missing-data and integrity checks, reproducible descriptive statistics, and GitHub, Zenodo, and SoftwareX release preparation. The software is released under the {profile['license_spdx']} license at {repository}. Future releases will add authenticated multi-user roles, encrypted restricted-data storage, configurable statistical-analysis plans, connectors to external model registries, and broader independent pilot evidence.

## Declarations

**Funding:** {profile['funding_statement'] or '[Author verification required]'}

**Declaration of competing interest:** {profile['conflict_statement'] or '[Author verification required]'}

**Data availability:** {profile['data_availability_statement'] or 'Aggregate evidence and synthetic examples may be released; participant-level data remain subject to consent, ethics, and governance restrictions.'}

**Generative AI use:** {profile['ai_use_statement'] or '[Author must insert the journal-compliant disclosure applicable at submission.]'}

**CRediT authorship contribution statement:** See the accompanying author-verification template.
"""


def _cover_letter(profile: Mapping[str, Any], readiness: Mapping[str, Any]) -> str:
    return f"""# Cover letter draft

Dear Editor,

Please consider our Original Software Publication, “{profile['manuscript_title']},” for publication in SoftwareX. HeritageGate is an open-source Python application that implements a stage-gated, rights-aware workflow for AI-assisted productization of motif-rich intangible cultural heritage. Its non-trivial software contribution is the executable coupling of authorization constraints, cultural-element records, model provenance, multi-role review, feedback rollback, market evidence, and asset and revenue governance.

The submitted release is version {profile['software_version']} under the {profile['license_spdx']} license. The software repository is {profile['repository_url'] or '[to be inserted]'}, the archived release is {profile['archive_url'] or '[to be inserted]'}, and the software DOI is {profile['software_doi'] or '[to be inserted]'}. The package includes installation instructions, examples, automated tests, data-quality checks, reproducible statistical reporting, and privacy-aware SoftwareX evidence exports.

The automated completeness checklist currently passes {readiness['passed']} of {readiness['total']} conditions. All empirical claims, ethics statements, consent records, author details, repository links, and archival identifiers must be verified by the authors before submission.

Sincerely,

{_author_names(profile)}
"""


def build_submission_release_package(
    engine: HeritageGateEngine,
    project_id: str,
    output_zip: str | Path,
    *,
    source_root: str | Path | None = None,
    seed: int = 20260729,
) -> dict[str, Any]:
    """Build a privacy-aware publication and software-release preparation bundle."""
    profile = engine.real_pilot.get_release_profile(project_id)
    if profile is None:
        raise ValueError("A release profile is required before building a submission package")
    output = Path(output_zip).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    project = engine.get_project(project_id)
    readiness = engine.real_pilot.release_readiness(project_id)
    results = engine.real_pilot.analysis_results(project_id, seed=seed)
    pilot_summary = engine.pilot.summary(project_id)

    with tempfile.TemporaryDirectory(prefix="heritagegate-v050-release-") as temp:
        root = Path(temp) / f"heritagegate-{_slug(project_id)}-v{profile['software_version']}-submission"
        public = root / "public_release"
        editorial = root / "editorial_submission"
        analysis = root / "aggregate_analysis"
        public.mkdir(parents=True)
        editorial.mkdir(parents=True)
        analysis.mkdir(parents=True)

        (public / "CITATION.cff").write_text(_citation_cff(profile), encoding="utf-8")
        (public / "codemeta.json").write_text(json.dumps(_codemeta(profile), ensure_ascii=False, indent=2), encoding="utf-8")
        (public / ".zenodo.json").write_text(json.dumps(_zenodo(profile), ensure_ascii=False, indent=2), encoding="utf-8")
        (public / "GitHub_RELEASE_NOTES.md").write_text(
            f"# HeritageGate {profile['software_version']}\n\n"
            "This release adds privacy-aware real-pilot enrollment, withdrawal handling, "
            "data-quality checks, deterministic analysis, and SoftwareX publication preparation.\n\n"
            "## Verification\n\nRun `python -m unittest discover -s tests -v` after installation.\n",
            encoding="utf-8",
        )
        (public / "README_RELEASE.md").write_text(
            f"# {profile['software_title']} {profile['software_version']}\n\n"
            f"Repository: {profile['repository_url'] or 'TO BE ADDED'}\n\n"
            f"Archived release: {profile['archive_url'] or 'TO BE ADDED'}\n\n"
            f"Software DOI: {profile['software_doi'] or 'TO BE ADDED'}\n\n"
            "Participant-level records, consent documents, source identifiers, and identity-token hashes "
            "are deliberately excluded from this public-release folder.\n",
            encoding="utf-8",
        )
        (public / "PRIVACY_EXCLUSION_LOG.md").write_text(
            "# Privacy exclusion log\n\n"
            "The release builder does not export participant rows, participant codes, consent references, "
            "consent-document files, identity-token hashes, source-row hashes, or raw session evidence. "
            "The pseudonymization key file is likewise never read or exported by the builder. "
            "Only aggregate metrics and structural metadata are included.\n",
            encoding="utf-8",
        )
        (public / "softwarex_metadata_tables.md").write_text(_metadata_tables(profile), encoding="utf-8")

        source = Path(source_root).expanduser().resolve() if source_root else Path(__file__).resolve().parents[2]
        for filename in ("LICENSE", "README.md", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md"):
            candidate = source / filename
            if candidate.is_file():
                shutil.copy2(candidate, public / filename)
        dist = source / "dist"
        if dist.is_dir():
            wheels = sorted(dist.glob(f"heritagegate-{profile['software_version']}-*.whl"))
            if wheels:
                shutil.copy2(wheels[-1], public / wheels[-1].name)

        (editorial / "SoftwareX_manuscript_draft.md").write_text(
            _manuscript_draft(project, profile, results, readiness), encoding="utf-8"
        )
        (editorial / "Highlights.txt").write_text(_highlights(), encoding="utf-8")
        (editorial / "Cover_letter_draft.md").write_text(_cover_letter(profile, readiness), encoding="utf-8")
        (editorial / "CRediT_author_statement_template.md").write_text(
            "# CRediT author statement template\n\n"
            "Replace placeholders only after every author approves the contribution statement.\n\n"
            "- Conceptualization: [names]\n- Methodology: [names]\n- Software: [names]\n"
            "- Validation: [names]\n- Formal analysis: [names]\n- Investigation: [names]\n"
            "- Data curation: [names]\n- Writing – original draft: [names]\n"
            "- Writing – review & editing: [names]\n- Visualization: [names]\n"
            "- Supervision: [names]\n- Project administration: [names]\n- Funding acquisition: [names]\n",
            encoding="utf-8",
        )
        (editorial / "Author_verification_required.md").write_text(
            "# Author verification required\n\n"
            "Verify authorship, affiliations, ORCID records, funding, competing interests, ethics status, "
            "consent wording, repository links, DOI, license, release date, all empirical values, and the "
            "journal's current generative-AI disclosure before submission. HeritageGate cannot verify these facts.\n",
            encoding="utf-8",
        )
        (editorial / "Data_availability_statement.md").write_text(
            profile["data_availability_statement"] or
            "Aggregate evidence and synthetic examples are available with the software release. Participant-level records are governed by the approved protocol, consent scope, and applicable access restrictions.\n",
            encoding="utf-8",
        )
        (editorial / "Generative_AI_use_declaration.md").write_text(
            profile["ai_use_statement"] or
            "[Insert the journal-compliant generative-AI use declaration applicable at the time of submission.]\n",
            encoding="utf-8",
        )

        (analysis / "aggregate_analysis_results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        aggregate = {
            "project_id": project_id,
            "schema_version": readiness["schema_version"],
            "participant_count": pilot_summary["participant_summary"]["total"],
            "installation_summary": pilot_summary["installation_summary"],
            "condition_summary": pilot_summary["condition_summary"],
            "sus_summary": pilot_summary["sus_summary"],
            "workflow_benchmark_summary": pilot_summary["workflow_benchmark_summary"],
            "participant_level_records_included": False,
        }
        (analysis / "public_aggregate_evidence.json").write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        readiness_rows = [
            {"check": key, "passed": bool(value), "author_action": "Verify or complete before submission" if not value else "Confirm evidence"}
            for key, value in readiness["checks"].items()
        ]
        _write_csv(editorial / "release_readiness_checklist.csv", readiness_rows)
        (editorial / "release_readiness.json").write_text(
            json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )

        package_meta = {
            "project_id": project_id,
            "software_version": profile["software_version"],
            "schema_version": readiness["schema_version"],
            "release_ready": readiness["ready"],
            "readiness_passed": readiness["passed"],
            "readiness_total": readiness["total"],
            "participant_level_records_included": False,
            "notice": "Generated materials require author verification and do not publish to GitHub or Zenodo automatically.",
        }
        (root / "package_metadata.json").write_text(
            json.dumps(package_meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        checksums = []
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
            checksums.append(f"{_sha256(path)}  {path.relative_to(root).as_posix()}")
        (root / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=f"{root.name}/{path.relative_to(root)}")

    return {
        "project_id": project_id,
        "output_zip": str(output),
        "software_version": profile["software_version"],
        "schema_version": readiness["schema_version"],
        "release_ready": readiness["ready"],
        "readiness_passed": readiness["passed"],
        "readiness_total": readiness["total"],
        "participant_level_records_included": False,
        "sha256": _sha256(output),
        "size_bytes": output.stat().st_size,
    }
