# Windows on Arm runner ReFS impact assessment

Assessment dated **13 November 2026** of 1,627 public GitHub Actions job definitions across 1,145 projects using standard Windows on Arm runners, with focused hosted setup-go verification.

## Reports and data

- [Word report](Windows-on-Arm-ReFS-impact-assessment.docx)
- [Complete job-by-job assessment (CSV)](job-impact.csv)
- [Shared setup-go exposure list (CSV)](shared-action-exposure.csv)

## Findings

The assessment examines [runner-images issue #15315](https://github.com/actions/runner-images/issues/15315), announcing D: reformatting to ReFS, and [issue #14878](https://github.com/actions/runner-images/issues/14878), requesting additional workspace/cache and Dev Drive changes.

- **D: ReFS with the Go tool-cache root on C: passed** cold installation and warm reuse for all four audited setup-go revisions.
- **Moving the tool-cache root to D: reproduced `EEXIST` on every cold installation**: the action creates a junction onto the same existing directory. Warm reuse passed. Keep the tool-cache root on C: or correct that path before moving it.
- Three jobs in goneovim and SQLite Browser are likely to fail **if workspace or runner temporary paths relocate**, because of hardcoded paths.
- Three additional jobs warrant targeted runtime validation.
- The tested setup-go revisions are referenced by 110 jobs across 67 projects. Those project jobs were not rerun; these are not 110 demonstrated failures.

Workspace, temporary-directory, and tool-cache relocation are **not confirmed by the announcement**. The report treats them separately from the announced filesystem change.

## Reproduce the setup-go check

The manual [verification workflow](.github/workflows/verify-setup-go.yml) uses the guarded first-step D: provisioning from [IronRDP PR #2186](https://github.com/Devolutions/IronRDP/pull/2186), without its workspace/Cargo/temp relocation. It runs two independent `windows-11-arm` jobs: D: ReFS with a C: tool-cache root, and the separate hypothetical D: tool-cache-root scenario. Both start with isolated empty caches, then check warm reuse, Go identity and a native hello-world build/run.

See [measured results, run links and reproduction instructions](verification/README.md) and [persistent per-job evidence](verification/results/2026-11-13.json). Eight final jobs produced twelve successful native Go compile/run checks and four reproduced conditional cold-install failures. The D: jobs intentionally remain red; their warm controls passed.

## Scope and limitations

This is a non-exhaustive public-project survey with bounded static analysis and controlled setup-go tests, not a rollout certification or failure-rate estimate. All 1,627 inventoried job definitions were inspected; some dependencies and entrypoints were unavailable or omitted. The CSVs retain the original static assessments.

Only this repository's verification workflow was run, on disposable hosted Arm VMs. The simulation uses a newly provisioned Dev Drive and an in-process cache-path override with unmodified action bundles; it is not the final rollout image. Original project workflows were not triggered, and no local disks were modified. Raw scan caches are not published here.
