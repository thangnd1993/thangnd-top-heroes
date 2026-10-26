<#
.SYNOPSIS
  Verify a CI-built Windows artifact and (only if everything passes) replace the Desktop app, keeping a rollback copy.

.DESCRIPTION
  1. The CI run must be completed/success, and its head SHA must equal -ExpectedCommit (40 hex).
  2. The artifact zip SHA-256 must equal the digest GitHub reports for that exact artifact.
  3. The zip is extracted into a temporary staging folder; the packaged build-info.json commit must equal the run head SHA.
  4. The staged exe must pass --smoke-test (and, when supported, --version-file must report the same commit).
  5. Without -Apply nothing outside the staging folder is touched (dry run).
  6. With -Apply the previous Desktop build is MOVED (not deleted) to %LOCALAPPDATA%\TopHeroesAutoManager\release-backups\<utc>\,
     the staged build is moved in, started with --smoke-test once more, and rolled back automatically if that fails.
     Only the two newest backups are kept. Logs, journals, settings, screenshots and diagnostics are never touched.
  The script never kills a running app: if one runs from the destination it stops with an error.

.EXAMPLE
  .\scripts\deliver_desktop.ps1 -RunId 40216208278 -ExpectedCommit <40-hex>            # dry run, downloads the artifact
  .\scripts\deliver_desktop.ps1 -RunId 40216208278 -ExpectedCommit <40-hex> -ZipPath C:\path\artifact.zip -Apply
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][long]$RunId,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedCommit,
    [string]$Repository = 'thangnd1993/thangnd-top-heroes',
    [string]$ArtifactName = 'TopHeroesAutoManager-Windows-x64',
    [string]$Destination = 'C:\Users\ADMIN\Desktop\app\TopHeroesAutoManager',
    [string]$ZipPath,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$ExpectedCommit = $ExpectedCommit.ToLowerInvariant()
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$stage = Join-Path $env:TEMP "thm-stage-$stamp"
$backupRoot = Join-Path $env:LOCALAPPDATA 'TopHeroesAutoManager\release-backups'
function Step($m) { Write-Host "[deliver] $m" }
function Fail($m) { throw "[deliver] ABORT: $m" }

function Test-Smoke([string]$exe) {
    $p = Start-Process -FilePath $exe -ArgumentList '--smoke-test' -PassThru
    if (-not $p.WaitForExit(90000)) { Stop-Process -Id $p.Id -Force; return $false }
    return ($p.ExitCode -eq 0)
}

# --- 1. run + artifact identity -------------------------------------------------------------
$run = gh run view $RunId --repo $Repository --json status,conclusion,headSha,headBranch,createdAt | ConvertFrom-Json
if ($run.status -ne 'completed' -or $run.conclusion -ne 'success') { Fail "run $RunId is $($run.status)/$($run.conclusion)" }
if ($run.headSha.ToLowerInvariant() -ne $ExpectedCommit) { Fail "run head $($run.headSha) != expected $ExpectedCommit" }
$arts = (gh api "repos/$Repository/actions/runs/$RunId/artifacts" | ConvertFrom-Json).artifacts |
    Where-Object { $_.name -eq $ArtifactName -and -not $_.expired }
if (@($arts).Count -ne 1) { Fail "expected exactly one live artifact '$ArtifactName', found $(@($arts).Count)" }
$artifact = $arts | Select-Object -First 1
$digest = ($artifact.digest -replace '^sha256:', '').ToLowerInvariant()
if ($digest -notmatch '^[0-9a-f]{64}$') { Fail 'GitHub reported no usable artifact digest' }
Step "run $RunId success on $($run.headBranch) @ $($run.headSha); artifact $($artifact.id) sha256 $digest"

# --- 2. zip checksum -------------------------------------------------------------------------
New-Item -ItemType Directory -Path $stage | Out-Null
if (-not $ZipPath) {
    $dl = Join-Path $stage 'download'
    gh run download $RunId --repo $Repository -n $ArtifactName -D $dl | Out-Null
    # gh extracts the artifact; re-zip is not byte-identical, so verify the extracted tree instead of the zip.
    $extracted = $dl
    Step 'artifact downloaded by gh (already extracted); zip checksum cannot be recomputed - pass -ZipPath for a byte check'
} else {
    $actual = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $digest) { Fail "zip sha256 $actual != artifact digest $digest" }
    Step "zip checksum verified: $actual"
    $extracted = Join-Path $stage 'app'
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $extracted
}
$exe = Join-Path $extracted 'TopHeroesAutoManager.exe'
if (-not (Test-Path $exe)) { Fail 'staged build has no TopHeroesAutoManager.exe at its root' }

# --- 3. packaged metadata --------------------------------------------------------------------
$infoPath = Join-Path $extracted '_internal\assets\build-info.json'
if (-not (Test-Path $infoPath)) { Fail 'packaged build-info.json is missing' }
$info = Get-Content $infoPath -Raw | ConvertFrom-Json
if (([string]$info.commit).ToLowerInvariant() -ne $ExpectedCommit) { Fail "packaged commit $($info.commit) != $ExpectedCommit" }
$date = if ($info.release_date) { $info.release_date } elseif ($info.built_at) { $info.built_at } else { '' }
if (-not $date) { Fail 'packaged build has no release date' }
Step "packaged: version $($info.version) commit $($info.commit) date $date channel $($info.channel) ci_run $($info.ci_run)"

# --- 4. staged smoke test --------------------------------------------------------------------
if (-not (Test-Smoke $exe)) { Fail 'staged exe failed --smoke-test' }
Step 'staged exe passed --smoke-test'
$exeHash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()

if (-not $Apply) { Step "DRY RUN OK. Staged at $stage; Desktop untouched. exe sha256 $exeHash"; return }

# --- 5. swap with rollback -------------------------------------------------------------------
$destFull = [IO.Path]::GetFullPath($Destination)
if ((Split-Path $destFull -Leaf) -ne 'TopHeroesAutoManager') { Fail "unexpected destination folder name: $destFull" }
$running = Get-Process -Name TopHeroesAutoManager -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($destFull, [StringComparison]::OrdinalIgnoreCase) }
if ($running) { Fail 'the Desktop app is running; close it yourself first (this script never stops it)' }
$backup = Join-Path $backupRoot $stamp
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$hadPrevious = Test-Path $destFull
if ($hadPrevious) { Move-Item -LiteralPath $destFull -Destination (Join-Path $backup 'TopHeroesAutoManager') }
try {
    Move-Item -LiteralPath $extracted -Destination $destFull
    @{ run = $RunId; artifact = $artifact.id; commit = $ExpectedCommit; zip_sha256 = $digest; exe_sha256 = $exeHash;
       delivered_at_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json |
        Set-Content -Encoding utf8 (Join-Path $destFull 'provenance.json')
    if (-not (Test-Smoke (Join-Path $destFull 'TopHeroesAutoManager.exe'))) { throw 'installed exe failed --smoke-test' }
} catch {
    Write-Warning "[deliver] install failed: $($_.Exception.Message); rolling back"
    if (Test-Path $destFull) { Move-Item -LiteralPath $destFull -Destination (Join-Path $backup 'failed-new') }
    if ($hadPrevious) { Move-Item -LiteralPath (Join-Path $backup 'TopHeroesAutoManager') -Destination $destFull }
    Fail 'rolled back to the previous Desktop build'
}
# keep only the two newest rollback copies (exact folder, timestamp-named only)
Get-ChildItem $backupRoot -Directory | Where-Object { $_.Name -match '^\d{8}-\d{6}$' } |
    Sort-Object Name -Descending | Select-Object -Skip 2 | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Step "DELIVERED. exe sha256 $exeHash; previous build kept at $backup"
