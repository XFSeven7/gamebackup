$ErrorActionPreference = "Stop"

$work = [IO.Path]::GetFullPath($PSScriptRoot)
$install = [IO.Directory]::GetParent($work).FullName
if ((Split-Path -Leaf $work) -notmatch '^\.gamebackup-update-[a-z0-9_]+$') { exit 1 }
$package = Join-Path $work "gamebackup"
$previous = Join-Path $work "previous"
$files = @("gamebackup.exe", "_internal")
$movedOld = @()
$movedNew = @()
$safeToClean = $false
$restartOld = $false
$updated = $null

function Move-ApplicationFile($source, $destination, $name) {
    $from = Join-Path $source $name
    $to = Join-Path $destination $name
    if ($name -eq "_internal") {
        [IO.Directory]::Move($from, $to)
    } else {
        [IO.File]::Move($from, $to)
    }
}

$errorMessage = $null
try {
    $running = Get-Process -Id ([int]$env:GAMEBACKUP_UPDATE_PID) -ErrorAction SilentlyContinue
    if ($running -and -not $running.WaitForExit(120000)) {
        throw "The current version did not exit in time. Please restart GameBackup and retry."
    }
    $restartOld = $true
    [IO.Directory]::CreateDirectory($previous) | Out-Null
    foreach ($name in $files) {
        Move-ApplicationFile $install $previous $name
        $movedOld += $name
    }
    foreach ($name in $files) {
        Move-ApplicationFile $package $install $name
        $movedNew += $name
    }
    $ready = Join-Path $work "ready"
    $env:GAMEBACKUP_UPDATE_READY = $ready
    try {
        $updated = Start-Process -FilePath (Join-Path $install "gamebackup.exe") -WorkingDirectory $install -PassThru
    } finally {
        Remove-Item Env:GAMEBACKUP_UPDATE_READY -ErrorAction SilentlyContinue
    }
    $startup = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path -LiteralPath $ready -PathType Leaf)) {
        if ($updated.WaitForExit(250) -or $startup.Elapsed.TotalSeconds -ge 45) {
            throw "The updated application did not finish starting."
        }
    }
    $safeToClean = $true
} catch {
    $errorMessage = $_.Exception.Message
    try {
        if ($updated -and -not $updated.HasExited) {
            $updated.Kill()
            if (-not $updated.WaitForExit(10000)) { throw "Unable to stop the updated application." }
        }
        foreach ($name in $movedNew) { Move-ApplicationFile $install $package $name }
        foreach ($name in $movedOld) { Move-ApplicationFile $previous $install $name }
        $safeToClean = $true
        if ($restartOld) {
            Start-Process -FilePath (Join-Path $install "gamebackup.exe") -WorkingDirectory $install
        }
    } catch {
        $errorMessage += "`nRecovery: " + $_.Exception.Message + "`n" + $work
    }
}

if ($safeToClean) {
    try { [IO.Directory]::Delete($work, $true) } catch {}
}
if ($errorMessage) {
    try {
        $popup = New-Object -ComObject WScript.Shell
        $popup.Popup($errorMessage, 15, "GameBackup update failed", 16) | Out-Null
    } catch {}
    exit 1
}
