$ErrorActionPreference = 'Stop'
$redRoot = Split-Path -Parent $PSScriptRoot
$redRuntime = Join-Path $redRoot 'runtime\ollama'
$redOllama = Join-Path $redRuntime 'ollama.exe'
if (-not (Test-Path -LiteralPath $redOllama)) {
    $redRelease = Invoke-RestMethod -Uri 'https://api.github.com/repos/ollama/ollama/releases/latest'
    $redAsset = $redRelease.assets | Where-Object name -eq 'ollama-windows-amd64.zip' | Select-Object -First 1
    if (-not $redAsset) { throw 'Archive officielle Ollama introuvable.' }
    New-Item -ItemType Directory -Force -Path (Join-Path $redRoot '.cache'),$redRuntime | Out-Null
    $redArchive = Join-Path $redRoot ('.cache\ollama-' + $redRelease.tag_name + '.zip')
    Write-Host "Telechargement Ollama $($redRelease.tag_name)..."
    if (-not (Test-Path -LiteralPath $redArchive) -or (Get-Item -LiteralPath $redArchive).Length -ne $redAsset.size) {
        & curl.exe --fail --location --retry 5 --continue-at - --output $redArchive $redAsset.browser_download_url --silent --show-error
        if ($LASTEXITCODE -ne 0) { throw 'Telechargement Ollama incomplet ; relance pour reprendre.' }
    }
    if ((Get-Item -LiteralPath $redArchive).Length -ne $redAsset.size) { throw 'Taille archive Ollama incorrecte.' }
    if ($redAsset.digest -like 'sha256:*') {
        if ((Get-FileHash -LiteralPath $redArchive -Algorithm SHA256).Hash -ne $redAsset.digest.Substring(7)) { throw 'Empreinte SHA256 Ollama incorrecte.' }
    }
    Write-Host 'Extraction Ollama...'
    Expand-Archive -LiteralPath $redArchive -DestinationPath $redRuntime -Force
}
$env:OLLAMA_MODELS = Join-Path $redRoot 'models\ollama'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_NUM_PARALLEL = '1'
$redRunning = $false
try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2; $redRunning = $true } catch {}
if (-not $redRunning) {
    New-Item -ItemType Directory -Force -Path (Join-Path $redRoot 'logs') | Out-Null
    Start-Process -FilePath $redOllama -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $redRoot 'logs\ollama-out.log') -RedirectStandardError (Join-Path $redRoot 'logs\ollama-err.log') | Out-Null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 1; $redRunning = $true; break } catch {}
    }
    if (-not $redRunning) { throw 'Ollama ne demarre pas. Consulte logs\ollama-err.log.' }
}
Write-Host 'Telechargement du modele local qwen3.5:2b...'
& $redOllama pull qwen3.5:2b
if ($LASTEXITCODE -ne 0) { throw 'Modele Ollama incomplet ; relance pour reprendre.' }
