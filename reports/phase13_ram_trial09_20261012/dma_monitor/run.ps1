param([Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'D:/fft/fft_phase13_structure_opt'
& D:/VivadoMM/2026.1/Vivado/bin/vivado.bat -mode batch -notrace -nojournal -log "$OutputRoot/vivado.log" -source "$OutputRoot/measure_imon.tcl" -tclargs "$OutputRoot/imon.csv" 120
exit $LASTEXITCODE
