$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($env:GAMEBACKUP_PYTHON) {
    $Py = $env:GAMEBACKUP_PYTHON
} elseif (Test-Path "C:\Users\Seven\scoop\apps\python\current\python.exe") {
    $Py = "C:\Users\Seven\scoop\apps\python\current\python.exe"
} else {
    $Py = "python"
}

& $Py -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Py -m PyInstaller --noconfirm --clean gamebackup.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$OutDir = Join-Path $Root "dist\gamebackup"
$Zip = Join-Path $Root "dist\gamebackup-win64.zip"
if (-not (Test-Path (Join-Path $OutDir "gamebackup.exe"))) {
    Write-Error "没有生成 gamebackup.exe"
    exit 1
}
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path $OutDir -DestinationPath $Zip
Write-Host "ok $Zip"
