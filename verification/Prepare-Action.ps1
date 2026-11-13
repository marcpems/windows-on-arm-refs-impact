$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$source = '.\.probe\setup-go'
$state = Get-Content '.\verification-results\before.json' -Raw | ConvertFrom-Json
$commit = (& git -C $source rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -cne $state.actionSha) {
    throw 'The downloaded action does not match the audited commit'
}
$manifestPath = Join-Path $source 'action.yml'
$manifest = Get-Content -LiteralPath $manifestPath -Raw
$main = [regex]'(?m)^  main: ''dist/setup/index.js''\r?$'
if ($main.Matches($manifest).Count -ne 1) {
    throw 'Expected exactly one official setup entrypoint'
}
$runtime = [regex]::Match($manifest, "(?m)^  using: '(node20|node24)'\r?$").Groups[1].Value
if (-not $runtime) { throw 'Unexpected action runtime' }
$state | Add-Member -NotePropertyName executionMode -NotePropertyValue 'Official pinned bundle, original Node runtime, in-process cache override'
$state | Add-Member -NotePropertyName nodeRuntime -NotePropertyValue $runtime
$state | Add-Member -NotePropertyName bundleSha256 -NotePropertyValue (
    Get-FileHash (Join-Path $source 'dist\setup\index.js') -Algorithm SHA256
).Hash
$state | ConvertTo-Json -Depth 8 | Set-Content '.\verification-results\before.json'
$main.Replace($manifest, "  main: 'probe-bootstrap.cjs'") | Set-Content -LiteralPath $manifestPath
Copy-Item '.\verification\Invoke-SetupGo.cjs' (Join-Path $source 'probe-bootstrap.cjs')
& git -C $source diff --exit-code -- dist/setup/index.js
if ($LASTEXITCODE -ne 0) { throw 'Official action bundle was modified' }
Write-Host "Verified official bundle at $commit ($runtime); only the entrypoint wraps the reserved cache variable"
