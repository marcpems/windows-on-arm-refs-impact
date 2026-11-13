"""Local guard tests: storage cmdlets are replaced, never invoked on this machine."""

import base64
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.load(
    (ROOT / ".github" / "workflows" / "verify-setup-go.yml").read_text(),
    Loader=yaml.BaseLoader,
)
STORAGE = WORKFLOW["jobs"]["verify"]["steps"][0]["run"]
PWSH = shutil.which("pwsh")
DISK = {
    "Number": 1,
    "BusType": "NVMe",
    "PartitionStyle": "RAW",
    "IsBoot": False,
    "IsSystem": False,
    "IsOffline": False,
    "IsReadOnly": False,
    "NumberOfPartitions": 0,
    "Size": 220 * 1024**3,
}


def powershell(script):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


class WorkflowTests(unittest.TestCase):
    def test_manual_bounded_two_scenario_workflow(self):
        self.assertEqual(list(WORKFLOW["on"]), ["workflow_dispatch"])
        job = WORKFLOW["jobs"]["verify"]
        self.assertEqual(job["runs-on"], "windows-11-arm")
        self.assertEqual(job["timeout-minutes"], "20")
        self.assertEqual(
            job["strategy"]["matrix"]["scenario"],
            ["d-only-cache-c", "hypothetical-cache-d"],
        )
        self.assertNotIn("uses", job["steps"][0])
        self.assertIn("Initialize-Disk", job["steps"][0]["run"])

    def test_all_action_choices_force_probe_cache_and_keep_failure_evidence(self):
        steps = WORKFLOW["jobs"]["verify"]["steps"]
        actions = [step for step in steps if step.get("uses") == "./.probe/setup-go"]
        self.assertEqual(len(actions), 8)
        choices = WORKFLOW["on"]["workflow_dispatch"]["inputs"]["setup_go"]["options"]
        for choice, action in zip(choices, actions[:4]):
            with self.subTest(choice=choice):
                self.assertEqual(action["if"], f"inputs.setup_go == '{choice}'")
                self.assertEqual(action["env"]["PROBE_TOOL_CACHE"], "${{ steps.prepare.outputs.toolcache }}")
                self.assertEqual(action["with"]["cache"], "false")
                self.assertEqual(action["with"]["architecture"], "arm64")
                self.assertEqual(action["continue-on-error"], "true")
        for choice, cold, warm in zip(choices, actions[:4], actions[4:]):
            self.assertEqual(cold["uses"], warm["uses"])
            self.assertEqual(cold["with"], warm["with"])
            self.assertEqual(cold["env"], warm["env"])
            self.assertIn(f"inputs.setup_go == '{choice}'", warm["if"])
            self.assertIn("steps.warm-ready.outcome == 'success'", warm["if"])
        for phase, selected in [("cold", actions[:4]), ("warm", actions[4:])]:
            verify = next(step for step in steps if step.get("id") == phase)
            self.assertIn("always()", verify["if"])
            for action in selected:
                self.assertIn(f"steps.{action['id']}.outcome", verify["env"]["SETUP_OUTCOME"])
        gate = next(step for step in steps if step.get("run") == r".\verification\Assert-ProbeResults.ps1")
        self.assertNotIn("continue-on-error", gate)
        self.assertIn("always()", gate["if"])

    def test_reserved_cache_override_runs_before_unmodified_bundle(self):
        steps = WORKFLOW["jobs"]["verify"]["steps"]
        checkout = next(step for step in steps if step.get("with", {}).get("repository") == "actions/setup-go")
        self.assertEqual(checkout["with"]["ref"], "${{ steps.prepare.outputs.action_sha }}")
        wrapper = (ROOT / "verification" / "Invoke-SetupGo.cjs").read_text()
        self.assertLess(wrapper.index("process.env.RUNNER_TOOL_CACHE ="), wrapper.index("require("))
        prepare = (ROOT / "verification" / "Prepare-Action.ps1").read_text()
        self.assertIn("diff --exit-code -- dist/setup/index.js", prepare)
        self.assertIn("node20|node24", prepare)
        for step in steps:
            self.assertNotIn("RUNNER_TOOL_CACHE", step.get("env", {}))

    def test_bootstrap_supplies_cache_to_bundle_and_rejects_bad_inputs(self):
        source = (ROOT / "verification" / "Invoke-SetupGo.cjs").read_text()
        harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = SOURCE;
const target = 'D:\\setup-go-probe\\' + 'a'.repeat(32) + '\\toolcache';
for (const [platform, cache, hosted, expected] of [
  ['win32', target, 'github-hosted', true],
  ['linux', target, 'github-hosted', false],
  ['win32', 'D:\\uncontrolled', 'github-hosted', false],
  ['win32', target, 'self-hosted', false],
]) {
  let imported = false;
  const env = {GITHUB_ACTIONS: 'true', RUNNER_ENVIRONMENT: hosted,
    PROBE_TOOL_CACHE: cache, RUNNER_TOOL_CACHE: 'C:\\native'};
  const execute = () => vm.runInNewContext(source, {
    process: {env, platform, version: 'test', arch: 'arm64'},
    console: {log() {}},
    require(path) {
      assert.equal(path, './dist/setup/index.js');
      assert.equal(env.RUNNER_TOOL_CACHE, target);
      imported = true;
    },
  });
  if (expected) execute(); else assert.throws(execute);
  assert.equal(imported, expected);
}
"""
        subprocess.run(["node", "-e", harness.replace("SOURCE", json.dumps(source))], check=True)

    def test_powershell_parses(self):
        scripts = [STORAGE] + [path.read_text() for path in (ROOT / "verification").glob("*.ps1")]
        for script in scripts:
            payload = base64.b64encode(script.encode()).decode()
            powershell(
                "$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
                + payload
                + "')); $tokens=$null; $errors=$null; "
                "[void][System.Management.Automation.Language.Parser]::ParseInput("
                "$source,[ref]$tokens,[ref]$errors); "
                "if ($errors.Count) { $errors | Out-String | Write-Error; exit 1 }"
            )

    def run_guard(self, *, disks=None, partitions=None, volumes=None, drives=None, env=None, format_fails=False):
        fixture = {
            "disks": [copy.deepcopy(DISK)] if disks is None else disks,
            "partitions": [] if partitions is None else partitions,
            "volumes": [] if volumes is None else volumes,
            "drives": [] if drives is None else drives,
            "formatFails": format_fails,
            "env": {
                "GITHUB_ACTIONS": "true", "HOST_ENVIRONMENT": "github-hosted",
                "RUNNER_ENVIRONMENT": "github-hosted", "HOST_OS": "Windows",
                "HOST_ARCH": "ARM64", "TEST_OS_ARCH": "Arm64",
                "GITHUB_WORKSPACE": r"C:\work", "RUNNER_TEMP": r"C:\runner-temp",
                "TEMP": r"C:\temp", "TMP": r"C:\temp", "RUNNER_TOOL_CACHE": r"C:\tools",
            },
        }
        fixture["env"].update(env or {})
        # The only local write is an Actions-output stand-in under the repository.
        output = ROOT / "verification" / (".guard-output-" + uuid.uuid4().hex)
        fixture["env"]["GITHUB_OUTPUT"] = str(output)
        payload = base64.b64encode(json.dumps(fixture).encode()).decode()
        source = STORAGE.replace(
            "[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture",
            "$env:TEST_OS_ARCH",
        )
        source = base64.b64encode(source.encode()).decode()
        harness = r"""
$ErrorActionPreference = 'Stop'
$fixture = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__FIXTURE__')) | ConvertFrom-Json
foreach ($property in $fixture.env.PSObject.Properties) {
    [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value)
}
$script:initializes = 0
$script:formats = 0
$script:newPartitions = 0
function Get-Disk { $fixture.disks }
function Get-Partition { $fixture.partitions }
function Get-Volume { param($DriveLetter); $fixture.volumes }
function Get-PSDrive { param($PSProvider); $fixture.drives }
function Test-Path { param($Path); return $true }
function Initialize-Disk {
    param($InputObject, $PartitionStyle, [switch]$PassThru)
    $script:initializes++
    if ($PartitionStyle -ne 'GPT' -or -not $PassThru) { throw 'Wrong initialization arguments' }
    return $InputObject
}
function New-Partition {
    param([Parameter(ValueFromPipeline)]$InputObject, [switch]$UseMaximumSize, $DriveLetter)
    process {
        $script:newPartitions++
        if ($DriveLetter -ne 'D' -or -not $UseMaximumSize) { throw 'Wrong partition arguments' }
        return [pscustomobject]@{ DriveLetter = 'D' }
    }
}
function Format-Volume {
    param([Parameter(ValueFromPipeline)]$InputObject, [switch]$DevDrive, $FileSystem, $NewFileSystemLabel, $Confirm)
    process {
        $script:formats++
        if (-not $DevDrive -or $FileSystem -ne 'ReFS' -or $Confirm) { throw 'Wrong format arguments' }
        if ($fixture.formatFails) { throw 'Injected formatting failure' }
        return [pscustomobject]@{ DriveLetter = 'D'; FileSystem = 'ReFS' }
    }
}
# Resolve every storage-related command to the in-memory function, never a real cmdlet.
foreach ($name in @('Get-Disk','Get-Partition','Get-Volume','Get-PSDrive','Test-Path',
                    'Initialize-Disk','New-Partition','Format-Volume')) {
    if ((Get-Command $name).CommandType -ne 'Function') { throw "Unmocked command: $name" }
}
$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__'))
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors)
$allowed = @('Get-Disk','Get-Partition','Get-Volume','Get-PSDrive','Test-Path',
             'Initialize-Disk','New-Partition','Format-Volume','ConvertTo-Json',
             'Write-Host','Format-Table','Where-Object')
foreach ($command in $ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.CommandAst]
}, $true)) {
    if ($command.GetCommandName() -notin $allowed) {
        throw "Refusing to execute an unreviewed workflow command: $($command.Extent.Text)"
    }
}
$errorText = $null
try { & ([scriptblock]::Create($source)) | Out-Null } catch { $errorText = $_.Exception.Message }
[ordered]@{
    error = $errorText
    initializes = $script:initializes
    newPartitions = $script:newPartitions
    formats = $script:formats
} | ConvertTo-Json -Compress
"""
        try:
            stdout = powershell(harness.replace("__FIXTURE__", payload).replace("__SOURCE__", source))
            return json.loads(stdout.splitlines()[-1])
        finally:
            output.unlink(missing_ok=True)

    def assert_rejected_without_writes(self, **fixture):
        result = self.run_guard(**fixture)
        self.assertIsNotNone(result["error"], result)
        self.assertEqual(
            (result["initializes"], result["newPartitions"], result["formats"]), (0, 0, 0), result
        )

    def test_only_one_eligible_unused_disk_is_provisioned(self):
        result = self.run_guard()
        self.assertIsNone(result["error"])
        self.assertEqual((result["initializes"], result["newPartitions"], result["formats"]), (1, 1, 1))

    def test_existing_refs_is_reused_without_writes(self):
        result = self.run_guard(
            partitions=[{"DriveLetter": "D", "DiskNumber": 2}],
            volumes=[{"DriveLetter": "D", "FileSystem": "ReFS"}],
        )
        self.assertEqual(result, {"error": None, "initializes": 0, "newPartitions": 0, "formats": 0})

    def test_existing_other_or_ambiguous_d_is_never_reformatted(self):
        for fixture in [
            {"volumes": [{"DriveLetter": "D", "FileSystem": "NTFS"}]},
            {"drives": [{"Name": "D"}]},
            {"partitions": [{"DriveLetter": "D", "DiskNumber": 1}]},
            {"volumes": [{"DriveLetter": "D", "FileSystem": "ReFS"}]},
            {"volumes": [{"DriveLetter": "D", "FileSystem": "ReFS"}] * 2},
        ]:
            with self.subTest(fixture=fixture):
                self.assert_rejected_without_writes(**fixture)

    def test_ineligible_disk_and_inventory_guards(self):
        for field, value in {
            "BusType": "SATA", "PartitionStyle": "GPT", "IsBoot": True,
            "IsSystem": True, "IsOffline": True, "IsReadOnly": True,
            "NumberOfPartitions": 1, "Size": 49 * 1024**3,
        }.items():
            with self.subTest(field=field):
                disk = dict(DISK, **{field: value})
                self.assert_rejected_without_writes(disks=[disk])
        self.assert_rejected_without_writes(disks=[])
        self.assert_rejected_without_writes(disks=[DISK, dict(DISK, Number=2)])
        self.assert_rejected_without_writes(partitions=[{"DiskNumber": 1, "DriveLetter": ""}])

    def test_hosting_and_architecture_guards(self):
        for name, value in {
            "GITHUB_ACTIONS": "false", "HOST_ENVIRONMENT": "self-hosted",
            "RUNNER_ENVIRONMENT": "self-hosted", "HOST_OS": "Linux",
            "HOST_ARCH": "X64", "TEST_OS_ARCH": "X64",
        }.items():
            with self.subTest(name=name):
                self.assert_rejected_without_writes(env={name: value})

    def test_partial_provisioning_failure_is_not_swallowed(self):
        result = self.run_guard(format_fails=True)
        self.assertEqual(result["error"], "Injected formatting failure")
        self.assertEqual(result["formats"], 1)

    def test_outcome_gate_never_turns_installation_failures_green(self):
        source = (ROOT / "verification" / "Assert-ProbeResults.ps1").read_text()
        source = base64.b64encode(source.encode()).decode()
        output = ROOT / "verification" / (".gate-output-" + uuid.uuid4().hex)
        try:
            for scenario, cold_ok, warm_ok, expected in [
                ("d-only-cache-c", True, True, None),
                ("d-only-cache-c", False, True, "Cold installation was not verified"),
                ("hypothetical-cache-d", False, True, "Cold installation was not verified"),
                ("hypothetical-cache-d", False, False, "Warm-cache verification failed"),
                ("hypothetical-cache-d", True, True, "Unexpected D: cold success"),
            ]:
                with self.subTest(scenario=scenario, cold_ok=cold_ok, warm_ok=warm_ok):
                    fixture = {
                        "state": {"scenario": scenario},
                        "cold": {
                            "setupOutcome": "success" if cold_ok else "failure",
                            "status": "verified-success" if cold_ok else "failed",
                            "logical": r"D:\cache\go\1.25.0\arm64",
                            "physical": r"D:\cache\go\1.25.0\arm64",
                            "error": None if cold_ok else "Injected setup-go failure",
                        },
                        "warm": {
                            "setupOutcome": "success" if warm_ok else "failure",
                            "status": "verified-success" if warm_ok else "failed",
                            "warmCacheUnchanged": warm_ok,
                        },
                        "output": str(output),
                    }
                    payload = base64.b64encode(json.dumps(fixture).encode()).decode()
                    harness = r"""
$fixture = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__FIXTURE__')) | ConvertFrom-Json
$env:GITHUB_STEP_SUMMARY = $fixture.output
function Get-Content {
    param($Path, [switch]$Raw)
    switch -Wildcard ($Path) {
        '*\before.json' { $fixture.state | ConvertTo-Json }
        '*\cold.json' { $fixture.cold | ConvertTo-Json }
        '*\warm.json' { $fixture.warm | ConvertTo-Json }
        default { throw "Unexpected read: $Path" }
    }
}
$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SOURCE__'))
$errorText = $null
try { & ([scriptblock]::Create($source)) | Out-Null } catch { $errorText = $_.Exception.Message }
@{ error = $errorText } | ConvertTo-Json -Compress
"""
                    result = json.loads(powershell(
                        harness.replace("__FIXTURE__", payload).replace("__SOURCE__", source)
                    ).splitlines()[-1])
                    if expected is None:
                        self.assertIsNone(result["error"])
                    else:
                        self.assertIn(expected, result["error"])
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    if PWSH is None:
        raise SystemExit("PowerShell 7 (pwsh) is required; no tests were run.")
    unittest.main(verbosity=2)
