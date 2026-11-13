$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$state = Get-Content '.\verification-results\before.json' -Raw | ConvertFrom-Json
$cold = Get-Content '.\verification-results\cold.json' -Raw | ConvertFrom-Json
$warm = Get-Content '.\verification-results\warm.json' -Raw | ConvertFrom-Json
if ($warm.setupOutcome -ne 'success' -or $warm.status -ne 'verified-success' -or
    -not $warm.warmCacheUnchanged) {
    throw 'Warm-cache verification failed; this is not the expected cold-only failure pattern'
}
if ($cold.setupOutcome -ne 'success' -or $cold.status -ne 'verified-success') {
    if ($state.scenario -eq 'hypothetical-cache-d' -and $cold.setupOutcome -eq 'failure' -and
        $cold.logical -ieq $cold.physical) {
        $message = 'D: cold install failed after populating a reusable cache, and warm reuse passed. This matches the predicted cold-only pattern; confirm EEXIST and identical junction paths in the cold setup-go log. The job deliberately remains failed.'
        Write-Host "::warning::$message"
        $message >> $env:GITHUB_STEP_SUMMARY
    }
    throw "Cold installation was not verified: $($cold.error)"
}
if ($state.scenario -eq 'hypothetical-cache-d') {
    throw 'Unexpected D: cold success: the predicted failure for this audited pin was not reproduced. Inspect source, environment and logs before changing the expectation.'
}
Write-Host 'Cold installation and unchanged warm reuse both passed native Go smoke tests'
