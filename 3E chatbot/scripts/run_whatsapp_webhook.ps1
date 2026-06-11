$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot

$env:CHATBOT_DISABLE_UI = '1'

if (Test-Path '.env') {
    Get-Content '.env' | ForEach-Object {
        if ($_ -match '^(\s*#|\s*$)') { return }
        $parts = $_ -split '=', 2
        if ($parts.Length -eq 2) {
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($name) { Set-Item -Path "Env:$name" -Value $value }
        }
    }
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $python = 'py'
    }
    else {
        $python = 'python'
    }
}

if ($python -eq 'py') {
    & $python -3 whatsapp_webhook.py
}
else {
    & $python whatsapp_webhook.py
}
