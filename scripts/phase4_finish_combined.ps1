param([string]$Candidate='D:\fft\iq_phase4_combined')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $Candidate
$deadline=(Get-Date).AddMinutes(60)
while ($true) {
    $simDone=(Get-Content -LiteralPath build\phase4_sim_v2_console.log -Tail 5) -match 'Completed stage: Sim'
    $softwareDone=$false
    if(Test-Path -LiteralPath build\phase4_software_v2_console.log) {
        $softwareDone=(Get-Content -LiteralPath build\phase4_software_v2_console.log -Tail 5) -match 'Completed stage: Software'
    }
    if($simDone -and $softwareDone) { break }
    if((Get-Date) -gt $deadline) { throw 'Combined build did not complete before the bounded wait expired' }
    Start-Sleep -Seconds 5
}
# Preserve and repeat the one short simulator stage that logged a transient
# startup directory diagnostic, without repeating the completed long core run.
New-Item -ItemType Directory -Path build\phase4_builder_startup_diagnostic | Out-Null
Copy-Item -LiteralPath build\logs\sim_builder.log -Destination build\phase4_builder_startup_diagnostic\original.log
& 'D:\VivadoMM\2026.1\Vivado\bin\vivado.bat' -mode batch -notrace -nojournal -log build/logs/sim_builder.log -source scripts/sim_builder.tcl *> build/phase4_builder_clean_console.log
if($LASTEXITCODE -ne 0) { throw 'Builder repeat failed' }
$builder=Get-Content -LiteralPath build\logs\sim_builder.log -Raw
if($builder -notmatch 'BUILDER_PASS' -or $builder -match 'ERROR:|Fatal:') { throw 'Builder repeat has unresolved diagnostics' }
python -X utf8 scripts/record_build_stage.py simulation *> build/phase4_final_sim_provenance.log
if($LASTEXITCODE -ne 0) { throw 'Final simulation provenance failed' }
python -c "import json; r=json.load(open('reports/hardware_validation.json')); assert r['setup_slack_ns']>=.10 and r['hold_slack_ns']>=0, r"
if($LASTEXITCODE -ne 0) { throw 'Combined timing margin gate failed' }
.\scripts\run.ps1 -Action Package *> build\phase4_package_console.log
if($LASTEXITCODE -ne 0) { throw 'Combined packaging failed' }
python -X utf8 scripts/deploy_board.py *> build/phase4_deploy_console.log
if($LASTEXITCODE -ne 0) { throw 'Combined deployment failed' }
python -X utf8 scripts/validate_board.py --suite full --out captures/phase4_combined_20260922 *> build/phase4_board_console.log
if($LASTEXITCODE -ne 0) { throw 'Combined basic board acceptance failed' }
Write-Host 'COMBINED_BASIC_ACCEPTANCE_PASS'
