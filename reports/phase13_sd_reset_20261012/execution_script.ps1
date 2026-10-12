$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'D:/fft/fft_phase13_structure_opt'
$env:PYTHONUTF8='1'
$env:IQ_CLIENT_SOURCE_IP='192.168.1.20'
$deadline=(Get-Date).AddHours(2)
while((Get-Date) -lt $deadline) {
    $log=Get-Content build/logs/phase13_ram_trial09_console.log -Raw
    if($log -match 'Traceback|Exception:|Failed:|failed'){throw 'RAM acceptance failed; SD remains unchanged'}
    if($log -match 'PHASE13_ALL_RAM_ACCEPTANCE_COMPLETE'){break}
    Start-Sleep -Seconds 5
}
if($log -notmatch 'PHASE13_ALL_RAM_ACCEPTANCE_COMPLETE'){throw 'RAM wait expired; SD remains unchanged'}
function Checked([string[]]$Arguments,[string]$Log) {
    & python @Arguments *> $Log
    if($LASTEXITCODE -ne 0){Get-Content -LiteralPath $Log -Tail 20;throw "Failed: $Arguments"}
    Write-Output "STAGE_PASS $Arguments"
}
Checked -Arguments @('scripts/verify_phase13_evidence.py') -Log 'build/logs/phase13_pre_sd_verify.log'
$install='reports/phase13_sd_install_20261012'
$reset='reports/phase13_sd_reset_20261012'
if((Test-Path -LiteralPath $install) -or (Test-Path -LiteralPath $reset)){throw 'Preserve previous SD attempt'}
Checked -Arguments @('scripts/phase13_sd_install.py','--write','--plan','build/phase13_sd_maintenance_trial09/plan.json','--out',$install) -Log 'build/logs/phase13_sd_install_console.log'
New-Item -ItemType Directory -Path $reset | Out-Null
Copy-Item -LiteralPath $PSCommandPath -Destination "$reset/execution_script.ps1"
Checked -Arguments @('.local/phase13_probe.py',"$reset/initial_state.json") -Log 'build/logs/phase13_sd_initial.log'
Checked -Arguments @('scripts/phase13_board_validation.py','--references','build/phase13_finite/reference_trial09/index.json','--out',"$reset/finite") -Log 'build/logs/phase13_sd_finite.log'
Checked -Arguments @('.local/phase13_probe.py',"$reset/final_state.json") -Log 'build/logs/phase13_sd_final.log'
Checked -Arguments @('scripts/record_phase13_deployment.py','sd','--installation',"$install/installation.json",'--finite',"$reset/finite/validation.json",'--final-state',"$reset/final_state.json") -Log 'build/logs/phase13_sd_record.log'
Write-Output 'PHASE13_SD_RESET_NUMERICAL_COMPLETE_FRESH_PHYSICAL_CYCLE_REQUIRED'
