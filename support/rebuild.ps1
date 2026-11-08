param(
    [Alias('Stage')]
    [ValidateSet('All','Reference','Hardware','Software','Sim','Finalize')]
    [string]$Action = 'All',
    [string]$VivadoRoot = 'D:\VivadoMM\2026.1\Vivado',
    [string]$VitisRoot = 'D:\VivadoMM\2026.1\Vitis',
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($projectRoot -match '[^\x00-\x7F]') {
    throw 'Copy the complete source tree to an ASCII-only path first, for example D:\phase13\project. See support\README.txt.'
}
try {
    $pythonCommand = Get-Command -Name $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $Python = $pythonCommand.Source
} catch {
    throw "Python executable is missing: $Python. Install Python 3.12 on PATH or supply -Python with an executable path."
}
$env:VIVADO_ROOT = $VivadoRoot
$env:XILINX_VITIS = $VitisRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$logRoot = Join-Path $projectRoot 'build\logs'
foreach ($relative in @('reports','artifacts','build\logs')) {
    New-Item -ItemType Directory -Path (Join-Path $projectRoot $relative) -Force | Out-Null
}
$requestedStages = if ($Action -eq 'All') { @('Reference','Hardware','Software','Sim','Finalize') } else { @($Action) }
if (@($requestedStages | Where-Object { $_ -in @('Reference','Hardware','Sim','Finalize') }).Count) {
    if (-not (Test-Path -LiteralPath (Join-Path $VivadoRoot 'bin\vivado.bat') -PathType Leaf)) {
        throw "Vivado 2026.1 is missing: $VivadoRoot"
    }
}
if (@($requestedStages | Where-Object { $_ -in @('Software','Finalize') }).Count) {
    if (-not (Test-Path -LiteralPath (Join-Path $VitisRoot 'bin\vitis.bat') -PathType Leaf)) {
        throw "Vitis 2026.1 is missing: $VitisRoot"
    }
}

function Run-Python([string[]]$Arguments) {
    & $Python -X utf8 @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python failed: $($Arguments -join ' ')" }
}

function Run-OriginalStage([string]$Name) {
    $logPath = Join-Path $logRoot ("support_" + $Name.ToLowerInvariant() + '.log')
    # Original run.ps1 checks every native command itself and throws on failure.
    & (Join-Path $projectRoot 'scripts\run.ps1') -Action $Name -VivadoRoot $VivadoRoot -VitisRoot $VitisRoot -Python $Python 2>&1 | Tee-Object -FilePath $logPath
}

$savedIqClientSourceIpPresent = Test-Path -LiteralPath Env:\IQ_CLIENT_SOURCE_IP
$savedIqClientSourceIp = $env:IQ_CLIENT_SOURCE_IP
Push-Location -LiteralPath $projectRoot
try {
    # Offline protocol tests use loopback sockets. A board-NIC source address
    # inherited from a user's normal capture session must not affect them.
    Remove-Item -LiteralPath Env:\IQ_CLIENT_SOURCE_IP -ErrorAction SilentlyContinue
    foreach ($stageName in $requestedStages) {
        Write-Host "SUPPORT_STAGE_START $stageName"
        if ($stageName -eq 'Hardware') {
            # This optional checkpoint is only produced when routed refinement
            # runs. Remove a previous generated copy so a retry cannot inspect it.
            $staleCheckpoint = Join-Path $projectRoot 'build\board\iq_board.runs\impl_1\system_wrapper_postroute_physopt.dcp'
            if (Test-Path -LiteralPath $staleCheckpoint -PathType Leaf) {
                Remove-Item -LiteralPath $staleCheckpoint -Force
            }
        }
        if ($stageName -eq 'Software') {
            Run-Python -Arguments @('scripts/phase4_build_config.py')
            Run-Python -Arguments @('support/run_software.py','--vitis-root',$VitisRoot)
        } elseif ($stageName -ne 'Finalize') {
            Run-OriginalStage $stageName
        } else {
            Run-Python -Arguments @('scripts/phase4_build_config.py','--check')
            Run-Python -Arguments @('scripts/record_build_stage.py','simulation','--check')
            Run-Python -Arguments @('scripts/record_build_stage.py','hardware','--check')
            Run-Python -Arguments @('scripts/verify_software.py')
            Run-Python -Arguments @('support/inspect_final_netlist.py','--vivado-root',$VivadoRoot)
            Run-Python -Arguments @('scripts/phase13_build_check.py')
            $psInit = Join-Path $projectRoot 'build\board\iq_board.gen\sources_1\bd\system\ip\system_ps7_0\ps7_init.tcl'
            if (-not (Test-Path -LiteralPath $psInit -PathType Leaf)) { throw "Missing PS initialization: $psInit" }
            Copy-Item -LiteralPath $psInit -Destination (Join-Path $projectRoot 'artifacts\ps7_init.tcl') -Force
            Push-Location -LiteralPath (Join-Path $projectRoot 'artifacts')
            try {
                foreach ($mode in @('sd','udp')) {
                    $bifText = "the_ROM_image:`n{`n  [bootloader] zynq_fsbl.elf`n  iq_analyzer.bit`n  iq_$mode.elf`n}`n"
                    Set-Content -LiteralPath "boot_$mode.bif" -Value $bifText -Encoding ascii
                    & (Join-Path $VitisRoot 'bin\bootgen.bat') -arch zynq -image "boot_$mode.bif" -o "BOOT_$mode.BIN" -w on
                    if ($LASTEXITCODE -ne 0) { throw "Bootgen failed for $mode" }
                }
                # Preserve the established build convention. The NETWORK image
                # is BOOT_udp.BIN; do not mistake this default SD-test image for it.
                Copy-Item -LiteralPath 'BOOT_sd.BIN' -Destination 'BOOT.BIN' -Force
            } finally { Pop-Location }
            Run-Python -Arguments @('scripts/record_boot_stage.py')
            Run-Python -Arguments @('scripts/record_boot_stage.py','--check')
            Run-Python -Arguments @('scripts/phase13_build_check.py')
        }
        Write-Host "SUPPORT_STAGE_PASS $stageName"
    }
    Write-Host "SUPPORT_REBUILD_PASS action=$Action"
    Write-Host 'Outputs are in artifacts/. This command does not program a board or write SD/QSPI.'
} finally {
    if ($savedIqClientSourceIpPresent) {
        Set-Item -LiteralPath Env:\IQ_CLIENT_SOURCE_IP -Value $savedIqClientSourceIp
    } else {
        Remove-Item -LiteralPath Env:\IQ_CLIENT_SOURCE_IP -ErrorAction SilentlyContinue
    }
    Pop-Location
}
