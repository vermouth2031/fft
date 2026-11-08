param(
 [ValidateSet('All','Reference','Sim','Hardware','RebuildHardware','Software','Package')][string]$Action='All',
 [string]$VivadoRoot='D:\VivadoMM\2026.1\Vivado',
 [string]$VitisRoot='D:\VivadoMM\2026.1\Vitis',
 [string]$Python='python'
)
$ErrorActionPreference='Stop'
# Current release entry points share the supported, Git-independent workflow.
if($Action -in @('All','Package')) {
 $targetAction=if($Action -eq 'All'){'All'}else{'Finalize'}
 & (Join-Path $PSScriptRoot '..\support\rebuild.ps1') -Action $targetAction -VivadoRoot $VivadoRoot -VitisRoot $VitisRoot -Python $Python
 return
}
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:VIVADO_ROOT=$VivadoRoot
$logRoot=Join-Path $projectRoot 'build\logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
function Run-Python([string[]]$Arguments) {
 & $Python @Arguments
 if($LASTEXITCODE -ne 0){throw "Python failed: $Arguments"}
}
function Run-Vivado([string]$Script) {
 $logName=Join-Path $logRoot (([IO.Path]::GetFileNameWithoutExtension($Script))+'.log')
 & (Join-Path $VivadoRoot 'bin\vivado.bat') -mode batch -notrace -nojournal -log $logName -source $Script
 if($LASTEXITCODE -ne 0){throw "Vivado failed: $Script (see $logName)"}
}
Run-Python -Arguments @('scripts/phase4_build_config.py')
if($Action -eq 'Reference') {
 Run-Python -Arguments @('-X','utf8','tests/generate_iq_vectors.py')
 Run-Python -Arguments @('tests/make_golden.py')
 Run-Python -Arguments @('tests/make_unit_vectors.py')
 Run-Python -Arguments @('tests/make_measurement_vectors.py')
 Run-Python -Arguments @('scripts/phase4_build_config.py')
}
if($Action -in @('Sim','Hardware')) {
 if(-not(Test-Path -LiteralPath 'build\vivado16k\iq_analyzer.xpr')){Run-Vivado 'scripts/create_fft.tcl'}
 Run-Python -Arguments @('scripts/verify_fft_config.py')
}
if($Action -eq 'Sim') {
 Run-Vivado 'scripts/sim_phase13_commit.tcl'
 Run-Vivado 'scripts/sim_units.tcl'
 Run-Python -Arguments @('tests/make_phase12_math_ranges.py')
 Run-Vivado 'scripts/sim_phase12_math_ranges.tcl'
 Run-Vivado 'scripts/sim_phase11_window.tcl'
 Run-Vivado 'scripts/sim_builder.tcl'
 Run-Python -Arguments @('tests/make_measurement_vectors.py')
 Run-Vivado 'scripts/sim_measurements.tcl'
 Run-Vivado 'scripts/sim_phase12_time_equivalence.tcl'
 Run-Python -Arguments @('tests/generate_digital_burst_vectors.py')
 Run-Vivado 'scripts/sim_digital_burst.tcl'
 Run-Vivado 'scripts/sim_spectrum_edges.tcl'
 Run-Vivado 'scripts/sim_phase10_equivalence.tcl'
 Run-Python -Arguments @('scripts/check_phase10_equivalence.py')
 Run-Python -Arguments @('scripts/sim_core_parallel.py')
 Run-Python -Arguments @('tests/check_core_results.py')
 Run-Python -Arguments @('scripts/analyze_latency.py','build/vivado16k/iq_analyzer.sim/sim_1/behav/xsim/latency_events.csv','--out','reports/phase2_latency_validation.json')
 Run-Vivado 'scripts/sim_axi.tcl'
 Run-Python -Arguments @('scripts/phase9_python_validation.py')
 Run-Python -Arguments @('scripts/record_build_stage.py','simulation')
}
if($Action -eq 'Hardware') {Run-Vivado 'scripts/build_board.tcl'}
if($Action -eq 'RebuildHardware') {Run-Vivado 'scripts/rebuild_board.tcl'}
if($Action -in @('Hardware','RebuildHardware')) {
 Run-Python -Arguments @('scripts/record_build_stage.py','hardware')
}
if($Action -eq 'Software') {
 $softwareLogPath=Join-Path $logRoot 'build_software.log'
 & (Join-Path $VitisRoot 'bin\vitis.bat') -s scripts/build_software.py *> $softwareLogPath
 $softwareLog=Get-Content -LiteralPath $softwareLogPath -Raw
 if($LASTEXITCODE -ne 0 -or $softwareLog -notmatch 'SOFTWARE_BUILD_PASS' -or $softwareLog -match 'Traceback') {
   Get-Content -LiteralPath $softwareLogPath -Tail 40
   throw "Vitis software build failed; inspect $softwareLogPath"
 }
}
Write-Host "Completed stage: $Action"
