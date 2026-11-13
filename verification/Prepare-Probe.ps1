$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
    $env:HOST_OS -ne 'Windows' -or $env:HOST_ARCH -ne 'ARM64') {
    throw 'This probe must run in its hosted Windows Arm workflow'
}
if ($env:GO_VERSION -notmatch '^\d+\.\d+\.\d+$') {
    throw 'go_version must be an exact stable version, for example 1.25.0'
}
if ($env:SCENARIO -notin @('d-only-cache-c', 'hypothetical-cache-d')) {
    throw 'Unknown scenario'
}
$baseline = $env:BASELINE_JSON | ConvertFrom-Json
foreach ($name in @('GITHUB_WORKSPACE', 'RUNNER_TEMP', 'TEMP', 'TMP', 'RUNNER_TOOL_CACHE')) {
    if ([Environment]::GetEnvironmentVariable($name) -cne $baseline.$name) {
        throw "Unexpected change to $name before the probe"
    }
}
if ($env:SCENARIO -eq 'd-only-cache-c' -and $baseline.RUNNER_TOOL_CACHE -notmatch '^[Cc]:\\') {
    throw 'The native tool cache is no longer on C:; this is not the assumed D:-only baseline'
}
if ((Get-Volume -DriveLetter D).FileSystem -ne 'ReFS') {
    throw 'D: must be ReFS'
}

# Both roots are new, including the C: cache's D: counterpart used internally by setup-go.
$suffix = "setup-go-probe\$([guid]::NewGuid().ToString('N'))\toolcache"
$cacheC = "C:\$suffix"
$cacheD = "D:\$suffix"
foreach ($root in @($cacheC, $cacheD)) {
    if (Test-Path -LiteralPath $root) { throw "Probe root already exists: $root" }
    New-Item -ItemType Directory -Path $root | Out-Null
    if (@(Get-ChildItem -LiteralPath $root -Force).Count -ne 0) {
        throw "Probe root is not empty: $root"
    }
}
$toolcache = if ($env:SCENARIO -eq 'd-only-cache-c') { $cacheC } else { $cacheD }
$revisions = @{
    'v7' = 'b7ad1dad31e06c5925ef5d2fc7ad053ef454303e'
    'v6' = '924ae3a1cded613372ab5595356fb5720e22ba16'
    'v5' = '40f1582b2485089dde7abd97c1529aa768e1baff'
    'audit-pin' = '4a3601121dd01d1626a1e23e37211e3254c1c06c'
}
if (-not $revisions.ContainsKey($env:ACTION_REVISION)) { throw 'Unknown action revision' }
$state = [ordered]@{
    scenario = $env:SCENARIO
    revision = $env:ACTION_REVISION
    actionSha = $revisions[$env:ACTION_REVISION]
    goVersion = $env:GO_VERSION
    architecture = 'arm64'
    toolcache = $toolcache
    cacheC = $cacheC
    cacheD = $cacheD
    baseline = $baseline
    coldCacheVerified = $true
    imageOS = $env:ImageOS
    imageVersion = $env:ImageVersion
    runUrl = "$env:GITHUB_SERVER_URL/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID"
    runAttempt = $env:GITHUB_RUN_ATTEMPT
    volumes = @(Get-Volume -DriveLetter C, D | Select-Object DriveLetter, FileSystem, Size, SizeRemaining)
}
New-Item -ItemType Directory -Path '.\verification-results' | Out-Null
$state | ConvertTo-Json -Depth 8 | Set-Content '.\verification-results\before.json'
"toolcache=$toolcache" >> $env:GITHUB_OUTPUT
Write-Host "Cold-install precondition verified: both roots are empty. Selected RUNNER_TOOL_CACHE=$toolcache"
Write-Host "Native cache left untouched: $($baseline.RUNNER_TOOL_CACHE)"
