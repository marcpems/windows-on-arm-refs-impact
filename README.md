# Windows on Arm runner ReFS impact assessment

Static assessment dated **13 November 2026** of 1,627 public GitHub Actions job definitions across 1,145 projects using standard Windows on Arm runners.

## Reports and data

- [Word report](Windows-on-Arm-ReFS-impact-assessment.docx)
- [Complete job-by-job assessment (CSV)](job-impact.csv)
- [Shared setup-go exposure list (CSV)](shared-action-exposure.csv)

## Findings

The assessment examines [runner-images issue #15315](https://github.com/actions/runner-images/issues/15315), announcing D: reformatting to ReFS, and [issue #14878](https://github.com/actions/runner-images/issues/14878), requesting additional workspace/cache and Dev Drive changes.

- No specific failure caused solely by D: reformatting was established in the inspected material.
- Three jobs in goneovim and SQLite Browser are likely to fail **if workspace or runner temporary paths relocate**, because of hardcoded paths.
- Three additional jobs warrant targeted runtime validation.
- Versions of `actions/setup-go` referenced by 110 jobs across 67 projects have a separate conditional failure path **if `RUNNER_TOOL_CACHE` moves to D: and an uncached Go version is installed**. These references are not 110 predicted failures.

Workspace, temporary-directory, and tool-cache relocation are **not confirmed by the announcement**. The report treats them separately from the announced filesystem change.

## Reproduce the setup-go check

The manual [verification workflow](.github/workflows/verify-setup-go.yml) uses the guarded first-step D: provisioning from [IronRDP PR #2186](https://github.com/Devolutions/IronRDP/pull/2186), without its workspace/Cargo/temp relocation. It runs two independent `windows-11-arm` jobs: D: ReFS with a C: tool-cache root, and the separate hypothetical D: tool-cache-root scenario. Both start with isolated empty caches, then check warm reuse, Go identity and a native hello-world build/run.

See [verification instructions, assertions, source evidence and limitations](verification/README.md). The workflow has **not been run**; adding it does not establish a runtime result.

## Scope and limitations

This is a non-exhaustive survey of public projects and a bounded static compatibility assessment, not a runtime certification or a prediction of failure rates. All 1,627 inventoried job definitions were inspected, with additional script and action-source analysis. Some dependencies and entrypoints were unavailable or omitted; see the report and per-job coverage notes.

No public workflows were triggered and no post-change runtime failures were demonstrated. Source evidence links are included in the report and CSVs. Raw scan caches are not published here.
