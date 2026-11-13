param([ValidateSet('cold', 'warm')][string]$Phase = 'cold')

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$state = Get-Content '.\verification-results\before.json' -Raw | ConvertFrom-Json
$relative = "go\$($state.goVersion)\arm64"
$logical = Join-Path $state.toolcache $relative
$physical = Join-Path $state.cacheD $relative
$result = [ordered]@{
    scenario = $state.scenario
    phase = $Phase
    actionSha = $state.actionSha
    setupOutcome = $env:SETUP_OUTCOME
    logical = $logical
    physical = $physical
    status = 'not-verified'
    error = $null
    paths = @()
}

function Assert-Link($Path, $Target, $LinkType) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.LinkType -ne $LinkType -or
        [IO.Path]::GetFullPath([string]$item.Target).TrimEnd('\') -ine
        [IO.Path]::GetFullPath($Target).TrimEnd('\')) {
        throw "Expected $LinkType at $Path targeting $Target; got $($item.LinkType) -> $($item.Target)"
    }
}

try {
    foreach ($path in @($logical, "$logical.complete", $physical, "$physical.complete") | Select-Object -Unique) {
        $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        $result.paths += if ($null -eq $item) {
            [ordered]@{ path = $path; exists = $false }
        } else {
            [ordered]@{
                path = $path; exists = $true; attributes = "$($item.Attributes)"
                linkType = $item.LinkType; target = $item.Target
            }
        }
    }
    $result.paths | ConvertTo-Json -Depth 5 | Write-Host
    foreach ($name in @('GITHUB_WORKSPACE', 'RUNNER_TEMP', 'TEMP', 'TMP')) {
        if ([Environment]::GetEnvironmentVariable($name) -cne $state.baseline.$name) {
            throw "Unexpected relocation of $name"
        }
    }
    if ($env:RUNNER_TOOL_CACHE -ine $state.toolcache) { throw 'Probe cache environment was not applied' }
    if ((Get-Volume -DriveLetter D).FileSystem -ne 'ReFS') { throw 'D: is no longer ReFS' }
    if ($env:SETUP_OUTCOME -ne 'success') {
        throw "setup-go outcome: $env:SETUP_OUTCOME. Inspect its log for the exact error; a network/download failure is not proof of the junction defect."
    }
    if (-not (Test-Path -LiteralPath "$physical.complete" -PathType Leaf)) {
        throw 'Physical D: installation lacks its completion marker'
    }
    if ($state.scenario -eq 'd-only-cache-c') {
        Assert-Link $logical $physical 'Junction'
        Assert-Link "$logical.complete" "$physical.complete" 'SymbolicLink'
    } elseif ((Get-Item -LiteralPath $physical -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'D: tool-cache entry should be an ordinary directory, not a self-link'
    }
    $expectedGo = Join-Path $logical 'bin\go.exe'
    $actualGo = (Get-Command go -CommandType Application).Source
    $result.goExecutable = $actualGo
    if ([IO.Path]::GetFullPath($actualGo) -ine [IO.Path]::GetFullPath($expectedGo)) {
        throw "PATH selected $actualGo instead of $expectedGo (possible preinstalled Go fallback)"
    }
    $goVersion = (& $actualGo version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $goVersion -cne "go version go$($state.goVersion) windows/arm64") {
        throw "Wrong Go version/architecture: $goVersion"
    }
    $result.goVersion = $goVersion
    $goEnvironment = & $actualGo env -json GOROOT GOOS GOARCH GOTOOLCHAIN
    if ($LASTEXITCODE -ne 0) { throw 'go env failed' }
    $result.goEnvironment = ($goEnvironment -join "`n") | ConvertFrom-Json
    if ($result.goEnvironment.GOOS -ne 'windows' -or $result.goEnvironment.GOARCH -ne 'arm64' -or
        $result.goEnvironment.GOTOOLCHAIN -ne 'local') {
        throw 'Go would not build locally for Windows Arm'
    }
    $goroot = [IO.Path]::GetFullPath($result.goEnvironment.GOROOT).TrimEnd('\')
    if ($goroot -ine $logical -and $goroot -ine $physical) { throw "Unexpected GOROOT: $goroot" }
    $result.sha256 = (Get-FileHash -LiteralPath $actualGo -Algorithm SHA256).Hash
    if ($result.sha256 -ne (Get-FileHash -LiteralPath (Join-Path $physical 'bin\go.exe') -Algorithm SHA256).Hash) {
        throw 'Logical and physical Go executable hashes differ'
    }
    if ($Phase -eq 'warm') {
        $snapshot = Get-Content '.\verification-results\warm-before.json' -Raw | ConvertFrom-Json
        $marker = Get-Item -LiteralPath "$physical.complete" -Force
        if ($snapshot.sha256 -ne $result.sha256 -or
            $snapshot.markerCreationTicks -ne $marker.CreationTimeUtc.Ticks -or
            $snapshot.markerWriteTicks -ne $marker.LastWriteTimeUtc.Ticks) {
            throw 'Warm invocation rewrote the tool-cache entry instead of reusing it'
        }
        $result.warmCacheUnchanged = $true
    }
    @'
package main
import ("fmt"; "runtime")
func main() { fmt.Printf("hello world: %s %s/%s", runtime.Version(), runtime.GOOS, runtime.GOARCH) }
'@ | Set-Content '.\verification-results\smoke.go'
    $smokeExecutable = ".\verification-results\smoke-$Phase.exe"
    & $actualGo build -o $smokeExecutable '.\verification-results\smoke.go'
    if ($LASTEXITCODE -ne 0) { throw 'Native smoke build failed' }
    $smoke = (& $smokeExecutable | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $smoke -cne "hello world: go$($state.goVersion) windows/arm64") {
        throw "Native smoke program failed: $smoke"
    }
    $result.smoke = $smoke
    $result.status = 'verified-success'
} catch {
    $result.status = 'failed'
    $result.error = $_.Exception.Message
    throw
} finally {
    $result | ConvertTo-Json -Depth 8 | Set-Content ".\verification-results\$Phase.json"
    @"
### setup-go: $($state.revision) / $($state.scenario) / $Phase
- Action commit: ``$($state.actionSha)``
- Go: ``$($state.goVersion)`` (``arm64``); cold-cache precondition: verified
- Tool-cache root: ``$($state.toolcache)``
- setup-go outcome: **$env:SETUP_OUTCOME**; verification: **$($result.status)**
- Error: $($result.error)
- See the setup-go step log and the uploaded JSON. A failed D: scenario is not evidence that the announcement relocates the tool cache.
"@ >> $env:GITHUB_STEP_SUMMARY
}
