# Gera o executável em dist\Transcritor de Reunioes\
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller

.\.venv\Scripts\pyinstaller.exe --noconfirm --windowed --onedir `
    --name "Transcritor de Reunioes" `
    --collect-all faster_whisper `
    --collect-binaries ctranslate2 `
    --collect-binaries onnxruntime `
    --collect-binaries pyaudiowpatch `
    transcritor.py

# Leva o modelo junto, para funcionar offline
$dist = "dist\Transcritor de Reunioes"
if ((Test-Path modelos) -and -not (Test-Path "$dist\modelos")) {
    Copy-Item -Recurse modelos "$dist\modelos"
}
Write-Host "Pronto: $dist\Transcritor de Reunioes.exe"
