param([switch]$Cpu)
$ErrorActionPreference = 'Stop'
$redRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $redRoot
$env:PYTHONUTF8 = '1'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $redRoot 'runtime\python'
$redUv = Join-Path $redRoot '.venv\Scripts\uv.exe'
if (-not (Test-Path -LiteralPath $redUv)) {
    throw 'Lance d''abord installer_red.bat pour installer Red et uv.'
}
& $redUv --system-certs --cache-dir .cache\uv python install 3.11 --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Installation Python 3.11 impossible.' }
$redNative = (& $redUv python find 3.11 --managed-python).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 introuvable.' }
$redPython = Join-Path $redRoot '.venv-chatterbox\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $redPython)) {
    & $redUv --cache-dir .cache\uv venv --seed --python $redNative .venv-chatterbox
    if ($LASTEXITCODE -ne 0) { throw 'Création environnement Chatterbox impossible.' }
}
$redIndex = 'https://download.pytorch.org/whl/cu118'
$redTorch = '2.6.0+cu118'
if ($Cpu) {
    $redIndex = 'https://download.pytorch.org/whl/cpu'
    $redTorch = '2.6.0+cpu'
}
& $redUv --system-certs --cache-dir .cache\uv pip install --python $redPython "torch==$redTorch" "torchaudio==$redTorch" --index-url $redIndex
if ($LASTEXITCODE -ne 0) { throw 'Installation PyTorch impossible.' }
& $redUv --system-certs --cache-dir .cache\uv pip install --python $redPython -r requirements-chatterbox.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation Chatterbox impossible.' }
& $redPython -u scripts\preparer_chatterbox.py
if ($LASTEXITCODE -ne 0) { throw 'Téléchargement des modèles incomplet.' }
Write-Host 'Chatterbox est installé. Ajoute tes WAV dans voices/ puis configure tts.moteur et tts.profil.'
Write-Host 'Test : .venv-red\Scripts\python.exe scripts\tester_chatterbox.py --profil jarvis'
