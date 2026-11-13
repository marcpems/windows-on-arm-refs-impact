$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$state = Get-Content '.\verification-results\before.json' -Raw | ConvertFrom-Json
$physical = Join-Path $state.cacheD "go\$($state.goVersion)\arm64"
$marker = Get-Item -LiteralPath "$physical.complete" -Force
$executable = Join-Path $physical 'bin\go.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw 'Cold attempt did not produce an executable; warm lookup cannot diagnose the junction path'
}
[ordered]@{
    physical = $physical
    markerCreationTicks = $marker.CreationTimeUtc.Ticks
    markerWriteTicks = $marker.LastWriteTimeUtc.Ticks
    sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
} | ConvertTo-Json | Set-Content '.\verification-results\warm-before.json'
Write-Host "Completed physical cache present at $physical; will verify unchanged marker and executable after reuse"
