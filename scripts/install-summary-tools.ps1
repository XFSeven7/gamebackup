$ErrorActionPreference = "Stop"

$BackupRoot = if ($env:GAMEBACKUP_ROOT) {
    $env:GAMEBACKUP_ROOT
} else {
    Join-Path $env:LOCALAPPDATA "gamebackup"
}
$ToolsDir = Join-Path $BackupRoot "tools"
$Files = @(
    @{
        Name = "UniversalSaveEditor.exe"
        Url = "https://github.com/Lucasifium/universal-save-editor/releases/download/v0.8.6/UniversalSaveEditor-0.8.6-windows-x64.exe"
        SHA256 = "377228a43147d834eebcee9c02d8f7c57613b0224a5054a6bba90dbcf3e41e01"
    }
    @{
        Name = "onimusha_items.tsv"
        Url = "https://raw.githubusercontent.com/Lucasifium/universal-save-editor/897f00561c5c848191477aa804b90be533328c9e/src/fmt/data/onimusha_items.tsv"
        SHA256 = "575074677cb084bb842313722e15b1910cc08787259831f56d3c31e114a02e6b"
    }
)

New-Item -ItemType Directory -Path $ToolsDir -Force | Out-Null
$DownloadSuffix = ".download-" + [guid]::NewGuid().ToString("N")
try {
    foreach ($File in $Files) {
        $Download = Join-Path $ToolsDir ($File.Name + $DownloadSuffix)
        Invoke-WebRequest -UseBasicParsing -Uri $File.Url -OutFile $Download
        if ((Get-FileHash -LiteralPath $Download -Algorithm SHA256).Hash -ne $File.SHA256) {
            throw "SHA256 verification failed for $($File.Name)."
        }
    }
    foreach ($File in $Files) {
        $Download = Join-Path $ToolsDir ($File.Name + $DownloadSuffix)
        Move-Item -LiteralPath $Download -Destination (Join-Path $ToolsDir $File.Name) -Force
    }
} finally {
    foreach ($File in $Files) {
        $Download = Join-Path $ToolsDir ($File.Name + $DownloadSuffix)
        if (Test-Path -LiteralPath $Download) {
            Remove-Item -LiteralPath $Download -Force
        }
    }
}

Write-Host "Save summary tools installed in $ToolsDir"
