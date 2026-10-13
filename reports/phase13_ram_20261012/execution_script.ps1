$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'D:/fft/fft_phase13_structure_opt'
$env:PYTHONUTF8='1'
$env:IQ_CLIENT_SOURCE_IP='192.168.1.20'
$ram='reports/phase13_ram_20261012'
$wide='reports/phase13_wideband_20261012'
foreach($destination in @($ram,$wide,'build/logs/phase13_program_board.log')) {
    if(Test-Path -LiteralPath $destination){throw "Existing acceptance attempt must be reviewed before retry: $destination"}
}
function Run-Checked([string[]]$Arguments,[string]$Log) {
    & python @Arguments *> $Log
    if($LASTEXITCODE -ne 0){Get-Content -LiteralPath $Log -Tail 30;throw "Failed: $Arguments"}
    Write-Output "STAGE_PASS $Arguments"
}
Run-Checked -Arguments @('scripts/phase13_build_check.py') -Log 'build/logs/phase13_preprogram_gate.txt'
Run-Checked -Arguments @('scripts/record_boot_stage.py','--check') -Log 'build/logs/phase13_preprogram_boot_gate.txt'
& D:/VivadoMM/2026.1/Vitis/bin/xsdb.bat scripts/program_board.tcl *> build/logs/phase13_program_board.log
if($LASTEXITCODE -ne 0){throw 'RAM programming failed'}
$programOutput=Get-Content -LiteralPath build/logs/phase13_program_board.log -Raw
if($programOutput -notmatch 'Firmware started' -or $programOutput -notmatch 'JTAG_PROCESSOR_RESET_BEFORE_ELF'){throw 'Missing RAM programming completion markers'}
Run-Checked -Arguments @('.local/phase13_probe.py','reports/phase13_programmed_board.json') -Log 'build/logs/phase13_programmed_probe.txt'
New-Item -ItemType Directory -Path $ram | Out-Null
Copy-Item -LiteralPath $PSCommandPath -Destination "$ram/execution_script.ps1"
Copy-Item -LiteralPath '.local/phase13_probe.py' -Destination "$ram/probe_source.py"
$reference='build/phase13_finite/reference_trial05/index.json'
$baseWide='reports/phase12_wideband_20261011/validation.json'
$baseContinuous='reports/phase12_ram_20261011/continuous300/stability.json'
Run-Checked -Arguments @('scripts/phase13_board_validation.py','--references',$reference,'--out',"$ram/finite") -Log "$ram/finite_console.txt"
Run-Checked -Arguments @('scripts/phase13_wideband_campaign.py','--project','.','--out',$wide,'--capture') -Log "$ram/wideband_console.txt"
Run-Checked -Arguments @('scripts/phase13_dma_validation.py','--switches','1000','--samples','32768','--out',"$ram/dma1000") -Log "$ram/dma1000_console.txt"
Run-Checked -Arguments @('scripts/phase13_wideband_stability.py','--seconds','60','--samples','32768','--out',"$ram/continuous60") -Log "$ram/continuous60_console.txt"
Run-Checked -Arguments @('scripts/phase13_wideband_stability.py','--seconds','300','--samples','32768','--out',"$ram/continuous300") -Log "$ram/continuous300_console.txt"
Run-Checked -Arguments @('.local/phase13_probe.py',"$ram/final_state.json") -Log "$ram/final_state_console.txt"
$reports=@('--finite',"$ram/finite/validation.json",'--wideband',"$wide/validation.json",'--baseline-wideband',$baseWide,'--baseline-continuous',$baseContinuous,'--dynamic',"$ram/dma1000/validation.json","$ram/continuous60/stability.json","$ram/continuous300/stability.json")
Run-Checked -Arguments (@('scripts/phase13_write_comparison.py')+$reports) -Log "$ram/comparison_console.txt"
Run-Checked -Arguments (@('scripts/record_phase13_acceptance.py')+$reports+@('--references',$reference,'--program-log','build/logs/phase13_program_board.log','--final-state',"$ram/final_state.json")) -Log 'build/logs/phase13_acceptance_record.txt'
Write-Output 'PHASE13_ALL_RAM_ACCEPTANCE_COMPLETE'
