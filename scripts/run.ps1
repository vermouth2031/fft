param(
 [ValidateSet('All','Reference','Sim','Hardware','RebuildHardware','Software','Package')][string]$Action='All',
 [string]$VivadoRoot='D:\VivadoMM\2026.1\Vivado',
 [string]$VitisRoot='D:\VivadoMM\2026.1\Vitis',
 [string]$Python='C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe'
)
$ErrorActionPreference='Stop'
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
if($Action -in @('All','Reference')) {
 Run-Python -Arguments @('-X','utf8','tests/generate_iq_vectors.py')
 Run-Python -Arguments @('tests/make_golden.py')
 Run-Python -Arguments @('tests/make_unit_vectors.py')
 Run-Python -Arguments @('tests/make_measurement_vectors.py')
}
if($Action -in @('All','Sim','Hardware')) {
 if(-not(Test-Path -LiteralPath 'build\vivado\iq_analyzer.xpr')){Run-Vivado 'scripts/create_fft.tcl'}
 Run-Python -Arguments @('scripts/verify_fft_config.py')
}
if($Action -in @('All','Sim')) {
 Run-Vivado 'scripts/sim_units.tcl'
 Run-Vivado 'scripts/sim_builder.tcl'
 Run-Python -Arguments @('tests/make_measurement_vectors.py')
 Run-Vivado 'scripts/sim_measurements.tcl'
 Run-Python -Arguments @('tests/generate_digital_burst_vectors.py')
 Run-Vivado 'scripts/sim_digital_burst.tcl'
 Run-Vivado 'scripts/sim_spectrum_edges.tcl'
 Run-Vivado 'scripts/sim_core.tcl'
 Run-Python -Arguments @('tests/check_core_results.py')
 Run-Python -Arguments @('scripts/analyze_latency.py','build/vivado/iq_analyzer.sim/sim_1/behav/xsim/latency_events.csv','--out','reports/phase2_latency_validation.json')
 Run-Vivado 'scripts/sim_axi.tcl'
 Run-Python -Arguments @('tests/check_host.py')
 Run-Python -Arguments @('tests/test_host_protocol.py')
 Run-Python -Arguments @('tests/test_frame_length_reference.py')
 Run-Python -Arguments @('tests/test_detector_host.py')
 Run-Python -Arguments @('tests/check_sd_parser.py')
 Run-Python -Arguments @('tests/test_qualification.py')
 Run-Python -Arguments @('scripts/record_build_stage.py','simulation')
}
if($Action -in @('All','Hardware')) {Run-Vivado 'scripts/build_board.tcl'}
if($Action -eq 'RebuildHardware') {Run-Vivado 'scripts/rebuild_board.tcl'}
if($Action -in @('All','Hardware','RebuildHardware')) {
 Run-Python -Arguments @('scripts/record_build_stage.py','hardware')
}
if($Action -in @('All','Software')) {
 $softwareLogPath=Join-Path $logRoot 'build_software.log'
 & (Join-Path $VitisRoot 'bin\vitis.bat') -s scripts/build_software.py *> $softwareLogPath
 $softwareLog=Get-Content -LiteralPath $softwareLogPath -Raw
 if($LASTEXITCODE -ne 0 -or $softwareLog -notmatch 'SOFTWARE_BUILD_PASS' -or $softwareLog -match 'Traceback') {
   Get-Content -LiteralPath $softwareLogPath -Tail 40
   throw "Vitis software build failed; inspect $softwareLogPath"
 }
}
if($Action -in @('All','Package')) {
 if(-not(Test-Path -LiteralPath 'reports\hardware_validation.json')){throw 'No timing-passed hardware validation report; rebuild hardware before packaging.'}
 Copy-Item -LiteralPath 'build\board\iq_board.gen\sources_1\bd\system\ip\system_ps7_0\ps7_init.tcl' -Destination 'artifacts\ps7_init.tcl' -Force
 Run-Python -Arguments @('scripts/verify_software.py')
 Run-Python -Arguments @('scripts/package_release.py','--check')
 Run-Python -Arguments @('scripts/write_build_report.py')
 Push-Location -LiteralPath 'artifacts'
 try {
   foreach($mode in @('sd','udp')) {
     $bif="the_ROM_image:`n{`n  [bootloader] zynq_fsbl.elf`n  iq_analyzer.bit`n  iq_$mode.elf`n}`n"
     Set-Content -LiteralPath "boot_$mode.bif" -Value $bif -Encoding ascii
     & (Join-Path $VitisRoot 'bin\bootgen.bat') -arch zynq -image "boot_$mode.bif" -o "BOOT_$mode.BIN" -w on
     if($LASTEXITCODE -ne 0){throw "bootgen failed for $mode"}
   }
   Copy-Item -LiteralPath 'BOOT_sd.BIN' -Destination 'BOOT.BIN' -Force
 } finally {Pop-Location}
 Run-Python -Arguments @('scripts/record_boot_stage.py')
 Run-Python -Arguments @('scripts/package_release.py')
}
Write-Host "Completed stage: $Action"
