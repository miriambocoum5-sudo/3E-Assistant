$ErrorActionPreference = 'Stop'

Write-Host "=== 3E Chatbot WhatsApp Starter ===" -ForegroundColor Cyan
Write-Host ""

$pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    $pythonExe = "py"
  }
  else {
    $pythonExe = "python"
  }
}

Write-Host "Starting webhook on port 5000..." -ForegroundColor Cyan

$webhookProcess = Start-Process -FilePath $pythonExe `
  -ArgumentList @("-3", "whatsapp_webhook.py") `
  -WorkingDirectory $PSScriptRoot `
  -PassThru `
  -NoNewWindow

Write-Host "Webhook started (PID: $($webhookProcess.Id))" -ForegroundColor Green
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Starting ngrok tunnel..." -ForegroundColor Cyan
Write-Host ""

ngrok http 5000

