param(
 [string]$Board = '192.168.1.10',
 [string]$Python = '',
 [ValidateSet('smoke','full')][string]$Suite = 'full'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not $Python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $Python = $pythonCommand.Source }
    else { throw 'Python was not found. Supply -Python with the Python 3 executable path.' }
}
$outRoot = Join-Path $projectRoot ('captures\acceptance_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
& $Python (Join-Path $PSScriptRoot 'validate_board.py') --board $Board --out $outRoot --suite $Suite
if ($LASTEXITCODE -ne 0) { throw "Board acceptance failed. Inspect $outRoot." }
Write-Host "Verified board results: $outRoot"
