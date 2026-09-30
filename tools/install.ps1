param([string]$Target = (Join-Path $env:LOCALAPPDATA 'Programs\Sorinote'), [string]$ExistingHome)
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'Sorinote'
if (-not (Test-Path -LiteralPath (Join-Path $source 'Sorinote.exe'))) { throw 'Sorinote.exe not found. Extract the complete ZIP first.' }
$targetFull = [IO.Path]::GetFullPath($Target)
$sourceFull = [IO.Path]::GetFullPath($source)
if ($targetFull -eq $sourceFull) { throw 'Choose an installation folder different from the package folder.' }
$running = Get-Process Sorinote -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $targetFull 'Sorinote.exe') }
if ($running) { throw 'Close Sorinote before installing or updating.' }
New-Item -ItemType Directory -Path $targetFull -Force | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $targetFull -Recurse -Force
$userFolder = Join-Path $env:LOCALAPPDATA 'Sorinote'
if ($ExistingHome) { $userFolder = [IO.Path]::GetFullPath($ExistingHome) }
New-Item -ItemType Directory -Path $userFolder -Force | Out-Null
$envPath = Join-Path $userFolder '.env.local'
if (-not (Test-Path -LiteralPath $envPath)) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination $envPath }
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $folder 'Sorinote.lnk'))
    $shortcut.TargetPath = Join-Path $targetFull 'Sorinote.exe'
    $shortcut.WorkingDirectory = $targetFull
    if ($ExistingHome) {
        $shortcut.Arguments = '--home "' + [IO.Path]::GetFullPath($ExistingHome) + '"'
    }
    $shortcut.Save()
}
Write-Output "Installed: $targetFull"
Write-Output "Credentials: $envPath"
Write-Output 'Updates preserve credentials and recordings. Open Sorinote from the desktop shortcut.'
