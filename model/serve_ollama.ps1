# Restart the local Ollama server with parallel slots.
# Usage: powershell -ExecutionPolicy Bypass -File serve_ollama.ps1 [-Parallel 8]
# (ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without BOM)
param([int]$Parallel = 8, [string]$Model = "exaone3.5:7.8b")

$exe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$vars = @{ OLLAMA_NUM_PARALLEL = "$Parallel"; OLLAMA_MAX_LOADED_MODELS = "1"; OLLAMA_KEEP_ALIVE = "30m"; OLLAMA_MAX_QUEUE = "512" }
foreach ($k in $vars.Keys) {
    [Environment]::SetEnvironmentVariable($k, $vars[$k], "User")   # also applies to the tray app after next login
    Set-Item "env:$k" $vars[$k]
}

Get-Process | Where-Object { $_.Name -like "ollama*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process -FilePath $exe -ArgumentList "serve" -WindowStyle Hidden

$v = $null
foreach ($i in 1..60) {
    try { $v = Invoke-RestMethod http://localhost:11434/api/version -TimeoutSec 2; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $v) { Write-Error "Ollama server did not start."; exit 1 }
Write-Output "Ollama $($v.version) running, parallel slots = $Parallel"

# preload the model so the first request is not slow
$body = @{ model = $Model; prompt = ""; keep_alive = "30m" } | ConvertTo-Json
Invoke-RestMethod http://localhost:11434/api/generate -Method Post -Body $body -ContentType "application/json" | Out-Null
(Invoke-RestMethod http://localhost:11434/api/ps).models | Select-Object name, size_vram, context_length
