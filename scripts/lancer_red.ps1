param([switch]$Diagnostic)
$ErrorActionPreference = 'Stop'
$redRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $redRoot
$env:PYTHONUTF8 = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$redPython = Join-Path $redRoot '.venv-red\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $redPython)) { throw 'Lance installer_red.bat avant le premier demarrage.' }
$redMode = & $redPython -c "from core.config import reglage; print(reglage('mode', 'local'))"
if ($LASTEXITCODE -ne 0) { throw 'Environnement incomplet : relance installer_red.bat.' }
if ($redMode.Trim() -eq 'local') {
    $redHost = (& $redPython -c "from core.config import reglage; print(reglage('ollama.hote', 'http://127.0.0.1:11434'))").Trim()
    $redRunning = $false
    try { $null = Invoke-RestMethod -Uri "$redHost/api/version" -TimeoutSec 2; $redRunning = $true } catch {}
    if (-not $redRunning) {
        if ($redHost -notmatch '^http://(localhost|127\.0\.0\.1):11434/?$') { throw "Serveur Ollama indisponible : $redHost" }
        $redOllama = Join-Path $redRoot 'runtime\ollama\ollama.exe'
        if (-not (Test-Path -LiteralPath $redOllama)) { throw 'Ollama absent : lance installer_red.bat.' }
        $env:OLLAMA_MODELS = Join-Path $redRoot 'models\ollama'
        $env:OLLAMA_HOST = '127.0.0.1:11434'
        $env:OLLAMA_NO_CLOUD = '1'
        $env:OLLAMA_CONTEXT_LENGTH = '4096'
        $env:OLLAMA_NUM_PARALLEL = '1'
        New-Item -ItemType Directory -Force -Path (Join-Path $redRoot 'logs') | Out-Null
        Start-Process -FilePath $redOllama -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $redRoot 'logs\ollama-out.log') -RedirectStandardError (Join-Path $redRoot 'logs\ollama-err.log') | Out-Null
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            try { $null = Invoke-RestMethod -Uri "$redHost/api/version" -TimeoutSec 1; $redRunning = $true; break } catch {}
        }
        if (-not $redRunning) { throw 'Ollama ne demarre pas. Consulte logs\ollama-err.log.' }
    }
    & $redPython -c "from core.llm import llm; import sys; sys.exit(0 if llm().disponible() else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Modele local absent : relance installer_red.bat.' }
}
if ($Diagnostic) { & $redPython -u scripts\doctor.py } else { & $redPython -u jarvis14.py }
exit $LASTEXITCODE
