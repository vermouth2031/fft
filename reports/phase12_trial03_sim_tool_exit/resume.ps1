$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'D:\fft\fft_phase12_wideband_150m'
$env:PYTHONUTF8='1'
$env:VIVADO_ROOT='D:\VivadoMM\2026.1\Vivado'
$env:IQ_CORE_WORKERS='4'
$env:IQ_CORE_HARDWARE_LOCK='D:\fft\fft_phase12_wideband_150m\.local\hardware_pending'
function Invoke-VivadoStage([string]$Stage) {
 & D:/VivadoMM/2026.1/Vivado/bin/vivado.bat -mode batch -notrace -nojournal -log "build/logs/$Stage.log" -source "scripts/$Stage.tcl"
 if($LASTEXITCODE -ne 0){throw "Vivado failed: $Stage"}
}
function Invoke-PythonStage([string[]]$Arguments) {
 & python @Arguments
 if($LASTEXITCODE -ne 0){throw "Python failed: $Arguments"}
}
Invoke-PythonStage -Arguments @('scripts/phase4_build_config.py','--check')
Invoke-VivadoStage 'sim_measurements'
Invoke-VivadoStage 'sim_phase12_time_equivalence'
Invoke-PythonStage -Arguments @('tests/generate_digital_burst_vectors.py')
Invoke-VivadoStage 'sim_digital_burst'
Invoke-VivadoStage 'sim_spectrum_edges'
Invoke-VivadoStage 'sim_phase10_equivalence'
Invoke-PythonStage -Arguments @('scripts/check_phase10_equivalence.py')
Invoke-PythonStage -Arguments @('scripts/sim_core_parallel.py')
Invoke-PythonStage -Arguments @('tests/check_core_results.py')
Invoke-PythonStage -Arguments @('scripts/analyze_latency.py','build/vivado16k/iq_analyzer.sim/sim_1/behav/xsim/latency_events.csv','--out','reports/phase2_latency_validation.json')
Invoke-VivadoStage 'sim_axi'
Invoke-PythonStage -Arguments @('scripts/phase9_python_validation.py')
Invoke-PythonStage -Arguments @('scripts/record_build_stage.py','simulation')
