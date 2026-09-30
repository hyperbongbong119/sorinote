$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)
npm.cmd run build
if ($LASTEXITCODE) { throw 'Frontend build failed' }
& .\.venv\Scripts\python.exe tools\acceptance.py
if ($LASTEXITCODE) { throw 'Regression tests failed' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath release Sorinote.spec
if ($LASTEXITCODE) { throw 'EXE build failed' }
Copy-Item tools\install.ps1,tools\install.cmd,.env.example -Destination release -Force
Copy-Item docs\desktop.md -Destination release\README.md -Force
Copy-Item docs\api-providers.md -Destination release\api-providers.md -Force
Compress-Archive -Path release\Sorinote,release\install.ps1,release\install.cmd,release\.env.example,release\README.md,release\api-providers.md -DestinationPath release\Sorinote-Windows.zip -Force
& .\.venv\Scripts\python.exe tools\verify_package.py
if ($LASTEXITCODE) { throw 'Package privacy check failed' }
Get-FileHash release\Sorinote-Windows.zip -Algorithm SHA256 | Format-List
