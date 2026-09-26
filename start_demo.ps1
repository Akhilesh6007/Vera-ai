$ErrorActionPreference = 'Stop'
$env:DEMO_PRELOAD_DATASET = 'true'
Start-Process -FilePath 'python' -ArgumentList '-m','uvicorn','app:app','--host','127.0.0.1','--port','8080' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
Start-Process -FilePath 'python' -ArgumentList '-m','http.server','8765','--bind','127.0.0.1','--directory',$PSScriptRoot -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
Write-Output 'Vera API: http://127.0.0.1:8080'
Write-Output 'Vera UI:  http://127.0.0.1:8765'
