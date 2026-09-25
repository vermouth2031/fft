$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'D:\fft\iq_analyzer'
$deadline = (Get-Date).AddMinutes(30)
while ($true) {
    $complete = (Get-Content -LiteralPath build\phase4_finish_combined_console.log -Tail 5) -match 'COMBINED_BASIC_ACCEPTANCE_PASS'
    if ($complete) { break }
    if ((Get-Date) -gt $deadline) { throw 'Combined acceptance did not finish within the bounded wait' }
    Start-Sleep -Seconds 5
}
python -X utf8 scripts/phase4_import_candidate.py --candidate D:/fft/iq_phase4_combined --backup build/phase4_pre_combined_import_20260922 *> build/phase4_import_console.log
if ($LASTEXITCODE -ne 0) { throw 'Candidate import failed' }
Write-Host 'FINAL_PRIMARY_IMPORT_PASS'
.\scripts\run.ps1 -Action Package *> build/phase4_primary_package_console.log
if ($LASTEXITCODE -ne 0) { throw 'Primary packaging failed' }
python -X utf8 scripts/maintenance/validate_sd.py --prepare *> build/phase4_sd_prepare_console.log
if ($LASTEXITCODE -ne 0) { throw 'SD validation preparation failed' }
python -X utf8 scripts/maintenance/validate_sd.py --build *> build/phase4_sd_build_console.log
if ($LASTEXITCODE -ne 0) { throw 'SD exporter build failed' }
python -X utf8 scripts/maintenance/validate_sd.py --out captures/phase4_sd_20260922 *> build/phase4_sd_console.log
if ($LASTEXITCODE -ne 0) { throw 'Actual SD application validation failed' }
Write-Host 'FINAL_PRIMARY_SD_APP_PASS'
python -X utf8 scripts/deploy_board.py *> build/phase4_primary_deploy_console.log
if ($LASTEXITCODE -ne 0) { throw 'Primary UDP deployment failed' }
python -X utf8 scripts/phase4_final_campaign.py prepare *> build/phase4_final_prepare_console.log
if ($LASTEXITCODE -ne 0) { throw 'Final references preparation failed' }
Write-Host 'FINAL_PRIMARY_REFERENCES_PASS'
python -X utf8 scripts/phase4_final_campaign.py capture *> build/phase4_final_capture_console.log
if ($LASTEXITCODE -ne 0) { throw 'Final board campaign failed' }
Write-Host 'FINAL_PRIMARY_CAMPAIGN_PASS'
