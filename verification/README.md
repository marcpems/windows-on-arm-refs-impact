# Verifying setup-go with D: ReFS

## Status and purpose

**Verified on 13 November 2026:** all four audited revisions passed cold installation and warm reuse with a C: tool-cache root and ReFS D:. All four reproduced the identical-path `EEXIST` junction error on a cold installation with the tool-cache root on D:; warm reuse passed. Keep the root on C: or correct that aliasing path before relocating it.

| Audited revision | C: cold / warm | D: cold / warm | Final run |
|---|---|---|---|
| v7 | Pass / Pass | EEXIST / Pass | [43444892689](https://github.com/marcpems/windows-on-arm-refs-impact/actions/runs/43444892689) |
| v6 | Pass / Pass | EEXIST / Pass | [43444901637](https://github.com/marcpems/windows-on-arm-refs-impact/actions/runs/43444901637) |
| v5 | Pass / Pass | EEXIST / Pass | [43444908827](https://github.com/marcpems/windows-on-arm-refs-impact/actions/runs/43444908827) |
| Additional audit pin | Pass / Pass | EEXIST / Pass | [43444915602](https://github.com/marcpems/windows-on-arm-refs-impact/actions/runs/43444915602) |

These eight jobs used `windows-11-arm`, image `win11-vs2026-arm64` version `20261101.203.1`, C: NTFS, D: ReFS and Go `1.25.0`. Twelve successful invocations compiled and ran native hello-world programs. Warm checks confirmed unchanged cache markers/hashes; C: checks verified the directory junction and completion-file symlink.

The four D: jobs **intentionally remain failed**; the exact error and successful warm controls establish the reproduction, not the red badge alone. [Persistent JSON evidence](results/2026-11-13.json) includes action/bundle identities, per-job paths, filesystem metadata, smoke results and error excerpts. Earlier harness-development runs are excluded: four had ineffective YAML cache overrides, and one selected every Go executable instead of the first PATH match. Both harness issues were fixed before the final runs.

The original CSVs remain a static survey. No original project jobs were rerun, and this result does not imply the announcement moves the tool cache.

[Issue #15315](https://github.com/actions/runner-images/issues/15315) announces D: ReFS starting 30 November, **not** workspace, temporary-directory or tool-cache relocation. The two jobs deliberately separate these questions:

| Job | Change under test | Observed result for the four audited revisions |
|---|---|---|
| `d-only-cache-c` | D: exists as ReFS; selected tool-cache root remains on C: | Cold setup-go copied Go to D:, created the C: junction and completion symlink, and passed the native smoke test. Warm reuse passed. |
| `hypothetical-cache-d` | D: ReFS **and** selected tool-cache root is on D: | Cold setup-go populated the cache, then failed with `EEXIST` on an identical-source/destination junction. Warm reuse and native execution passed. |

Both use fresh, randomly named tool-cache directories on the designated drive, not the runner's shared/preinstalled cache. This is a controlled drive-location test, **not an exact preservation of the native cache pathname or all its ACLs**. In the first job the native cache must initially be on C:; otherwise it stops rather than claiming the original baseline still holds. Workspace, `RUNNER_TEMP`, `TEMP` and `TMP` are recorded before provisioning and asserted unchanged afterward.

## Technique and safety

The **first user-defined step**, before checkout or setup-go, adapts the disk-selection guard from [marcpems's IronRDP PR #2186](https://github.com/Devolutions/IronRDP/pull/2186), [pinned implementation](https://github.com/Devolutions/IronRDP/blob/fb4b93cb0644306e3115f20ba8a3313de44ed700/.github/workflows/release-binaries.yml). GitHub's own runner/action initialization still precedes this step.

- Restricted to `windows-11-arm`, `github-hosted`, Windows and native Arm; self-hosted environments fail.
- Reuses an existing D: only if it is an ordinary ReFS volume. An existing non-ReFS or ambiguous D: fails without reformatting.
- Otherwise requires **exactly one** online, writable, non-boot/non-system, RAW NVMe disk of at least 50 GiB, with zero partitions and no partition-inventory entry.
- Only that unused disk is initialized as GPT and formatted using `Format-Volume -DevDrive -FileSystem ReFS`. No disk clearing, repartitioning of existing storage, AV changes, workspace junctions or temp relocation.
- Unlike IronRDP's optional optimization, missing/ambiguous storage **fails** the verification: a silent no-op would produce misleading results.

**Do not run the provisioning step locally or copy this workflow to a self-hosted runner.** The verification scripts are hosted-job helpers, not workstation setup instructions. The isolated directories live only for the disposable hosted VM's lifetime.

This tests today's runner with a newly provisioned Dev Drive (or a suitable existing ReFS D:), not the final rollout image, ReFS version, volume policy, security configuration or performance. There is no no-D:/NTFS control job.

## Run manually

After reviewing and publishing these files on the repository's default branch, open **Actions → Verify setup-go on Windows Arm ReFS → Run workflow**. There are no push, PR or scheduled triggers. Each dispatch starts **two** jobs, bounded to 20 minutes each.

Select one audited action revision:

| Input | Immutable action commit |
|---|---|
| `v7` (default) | `b7ad1dad31e06c5925ef5d2fc7ad053ef454303e` |
| `v6` | `924ae3a1cded613372ab5595356fb5720e22ba16` |
| `v5` | `40f1582b2485089dde7abd97c1529aa768e1baff` |
| `audit-pin` | `4a3601121dd01d1626a1e23e37211e3254c1c06c` |

The default Go `1.25.0` has a [Windows Arm package in actions/go-versions](https://github.com/actions/go-versions/releases/tag/1.25.0-16925932082). It is a fixed compatibility-test fixture, not a recommendation to deploy that Go version. Another exact stable version can be supplied if it has a Windows Arm distribution.

Optional CLI dispatch (this **starts hosted jobs**, so run only when intended):

```powershell
gh workflow run verify-setup-go.yml --repo marcpems/windows-on-arm-refs-impact -f setup_go=v7 -f go_version=1.25.0
gh run list --repo marcpems/windows-on-arm-refs-impact --workflow verify-setup-go.yml --limit 5
```

Dispatch other revisions individually only if needed; a v7 result does not certify every historical action bundle.

## Why this reaches the cold-install branch

`cache: false` disables Go dependency/build-cache integration; it **does not disable the hosted tool cache**. `check-latest: true` would not reliably force an installation either.

Instead, before setup-go starts, both the selected cache root and its C:/D: counterpart are newly created and asserted empty. The probe requests an exact version and `architecture: arm64`, and disables dependency caching. No installed versions are removed. A successful outcome must resolve `go.exe` from that exact root, not a preinstalled executable. `GOTOOLCHAIN=local` prevents automatic Go toolchain switching.

**Important harness correction:** the initial runs showed that the runner overwrites a step-level `RUNNER_TOOL_CACHE` override with its native value. Those runs did not exercise the requested isolated cache and are not counted as scenario results. The corrected probe checks out the selected immutable setup-go commit, retains its original action inputs and Node runtime, and adds a small entrypoint wrapper that sets `process.env.RUNNER_TOOL_CACHE` immediately before loading the **unmodified official compiled bundle**. The bundle hash and runtime are recorded. Only the manifest's main entrypoint changes; the installer code is not patched. Thus the D: case simulates the cache location seen by the action process, not a platform-level runner reconfiguration.

## Read the evidence

Each job uploads `verification-results` even on setup-go failure:

- `before.json`: source SHA, Go version, image identity, original paths, selected/empty cache roots, volume filesystems and run URL.
- `cold.json` and `warm.json`: actual action outcomes, logical/physical cache paths, directory/file link metadata, errors and, on success, Go environment/version, executable hash and native hello-world compile/run output.
- `warm-before.json`: physical completion-marker creation/write timestamps and Go executable hash captured before the second invocation. Warm success requires these to remain unchanged.
- On success, the smoke source and executable(s) are also included. Earlier preparation failures can leave only partial diagnostics; consult the job log.

The setup-go step logs contain the download/cache operation and exact exception. Keep/download those logs along with the artifact; JSON does not copy the action's stderr.

The installer catches an internal-distribution install error and retries the direct Go distribution. Consequently, a junction error may appear twice and the final error may say `Failed to download version ... EEXIST ...`. Read the nested error and source/destination paths, not just that wrapper wording.

`continue-on-error` is used **only to collect evidence and attempt the warm control**. A final, non-tolerated gate fails the job for any setup-go/verification failure, including the hypothesized D: defect. Thus a confirmed reproduction is expected to yield one green C: job and one red D: job, **not** a falsely green workflow. Missing evidence also fails. An unexpected D: cold success is explicitly flagged as a prediction not reproduced, rather than silently accepting a changed test path.

For the C: case, both cold and warm success require the directory junction to the physical D: installation and the separate `.complete` file symlink, a matching `go version ... windows/arm64`, the selected PATH/GOROOT, matching executable hashes, and a compiled/running native hello-world program. For the D: case, the gate distinguishes **cold failure with a completed cache and successful warm reuse** from a warm failure. A red badge or this pattern alone is not proof: confirm the action's **exact `EEXIST` junction error with identical source/destination paths** in its cold-step log. Download, authorization, unsupported-version, storage-preparation and runtime-startup errors are different failures and must not be reported as reproducing the defect. The official `uses:` action exposes no exception output, so the exact error is deliberately checked from the log rather than guessed from `outcome: failure`.

The warm action should log `Found in cache @ ...`; the cold action should log a download and cache population. Do not mistake setup-go's `cache-hit` output (dependency-cache integration) for this tool-cache lookup. The completed cache's timestamps/hash and both smoke tests provide independent reuse evidence.

A successful D:-only case supports compatibility for that action/version/image. A failing hypothetical relocation case does **not** imply that #15315 will cause that failure.

## Canonical source inspected

- [`getGo` and `cacheWindowsDir`, pinned v7](https://github.com/actions/setup-go/blob/b7ad1dad31e06c5925ef5d2fc7ad053ef454303e/src/installer.ts): first checks `tc.find`; the Windows cold-install branch substitutes C: → D:, calls `tc.cacheDir`, then unconditionally creates the directory junction and completion symlink.
- [Hosted-runner detection](https://github.com/actions/setup-go/blob/b7ad1dad31e06c5925ef5d2fc7ad053ef454303e/src/utils.ts) and [action entrypoint](https://github.com/actions/setup-go/blob/b7ad1dad31e06c5925ef5d2fc7ad053ef454303e/src/main.ts).
- The same routine was read at [v5](https://github.com/actions/setup-go/blob/40f1582b2485089dde7abd97c1529aa768e1baff/src/installer.ts), [v6](https://github.com/actions/setup-go/blob/924ae3a1cded613372ab5595356fb5720e22ba16/src/installer.ts), [the additional report pin](https://github.com/actions/setup-go/blob/4a3601121dd01d1626a1e23e37211e3254c1c06c/src/installer.ts), and [current main at inspection](https://github.com/actions/setup-go/blob/802e89cd7394b98352d79117a8b463bbfc2fdacf/src/installer.ts). All retain the same C: substitution/self-junction issue.

## Non-destructive local validation

From the repository root:

```powershell
actionlint .github\workflows\verify-setup-go.yml
python verification\test_workflow.py
```

These checks require PowerShell 7, Node.js, Python with PyYAML, and actionlint. The tests parse scripts, exercise the first-step guards with mocked storage commands, check the bootstrap with a mocked action bundle, and verify that the final outcome gate cannot hide failures. They never run actual disk commands. They do not substitute for hosted ReFS/Node/action verification.
