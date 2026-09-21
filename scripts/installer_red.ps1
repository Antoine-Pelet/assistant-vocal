$ErrorActionPreference = 'Stop'
$redRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $redRoot
$env:PYTHONUTF8 = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$redBootstrap = Join-Path $redRoot '.venv\Scripts\python.exe'
$redPython = Join-Path $redRoot '.venv-red\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $redBootstrap)) {
    py -3.13 -m venv (Join-Path $redRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Installe Python 3.13 depuis python.org puis relance.' }
}
& $redBootstrap -m pip install uv
if ($LASTEXITCODE -ne 0) { throw 'Installation uv incomplete.' }
$redUv = Join-Path $redRoot '.venv\Scripts\uv.exe'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $redRoot 'runtime\python'
& $redUv --cache-dir .cache\uv python install 3.13 --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Installation Python standard incomplete.' }
$redNative = (& $redUv python find 3.13 --managed-python).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Python standard introuvable.' }
if (-not (Test-Path -LiteralPath $redPython)) {
    & $redUv --cache-dir .cache\uv venv --seed --python $redNative .venv-red
    if ($LASTEXITCODE -ne 0) { throw 'Creation environnement Red impossible.' }
}
& $redUv --cache-dir .cache\uv pip install --python $redPython -r requirements-red.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation Python incomplete.' }
& $redPython -u scripts\preparer_red.py
if ($LASTEXITCODE -ne 0) { throw 'Preparation des modeles incomplete.' }
& (Join-Path $PSScriptRoot 'installer_ollama_red.ps1')
Write-Host 'Red est pret. Double-clique sur lancer_red.bat.'
