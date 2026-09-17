$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$py = 'C:\Users\LENOVO\AppData\Local\Programs\Python\Python312\python.exe'
$client = Join-Path $root 'host\iq_client.py'
$outRoot = Join-Path $root ('captures\network_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$adapter = @(Get-NetAdapter | Where-Object InterfaceGuid -eq '{E685DD6F-F3DC-4262-A662-E682DEBA6D43}')
if ($adapter.Count -ne 1 -or $adapter[0].Status -ne 'Up') {
    throw 'Ethernet link is down. Connect the board RJ45 port to this PC and power on the board.'
}
$ip = Get-NetIPAddress -InterfaceIndex $adapter[0].ifIndex -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -eq '192.168.1.20' -and $_.PrefixLength -eq 24 -and $_.AddressState -eq 'Preferred' }
if (-not $ip) { throw 'The wired adapter needs a usable static address 192.168.1.20/24.' }
if (Get-Process python,pythonw -ErrorAction SilentlyContinue | Where-Object MainWindowTitle -Like '*IQ*') {
    throw 'Close the IQ monitor before running the CLI captures.'
}
New-Item -ItemType Directory -Path $outRoot -ErrorAction Stop | Out-Null
$results = @()
$tests = @(
    @{ name='tone_once'; vector='tone_pos_fs4.bin'; seconds=0 },
    @{ name='qpsk_10s'; vector='qpsk_sps4.bin'; seconds=10 },
    @{ name='qpsk_60s'; vector='qpsk_sps4.bin'; seconds=60 }
)
try {
    foreach ($test in $tests) {
        Write-Host ('Starting ' + $test.name + '. Please wait for capture and export to finish.')
        $out = Join-Path $outRoot $test.name
        $arguments = @($client,'capture','--board','192.168.1.10','--vector',
            (Join-Path $root ('data\vectors\' + $test.vector)),'--window','hann','--out',$out)
        if ($test.seconds) { $arguments += @('--cyclic','--seconds',[string]$test.seconds) }
        & $py @arguments
        if ($LASTEXITCODE -ne 0) { throw ('Capture failed: ' + $test.name + '; inspect its capture.json') }
        $meta = Get-Content -LiteralPath (Join-Path $out 'capture.json') -Raw | ConvertFrom-Json
        foreach ($field in @('capture_complete','replay_readback_verified','frequency_sequence_valid')) {
            if ($meta.$field -ne $true) { throw ($test.name + ': failed ' + $field) }
        }
        foreach ($field in @('error_status','frequency_queue_dropped','burst_queue_dropped',
            'udp_missing_packet_count','frequency_records_missing','burst_records_missing','duplicate_frequency_records')) {
            if ($null -eq $meta.$field -or $meta.$field -ne 0) { throw ($test.name + ': nonzero or missing ' + $field) }
        }
        foreach ($field in @('hardware_max_latency_cycles','hardware_max_publish_latency_cycles')) {
            if ($null -eq $meta.$field -or $meta.$field -le 0 -or $meta.$field -gt 200000) {
                throw ($test.name + ': invalid or excessive ' + $field)
            }
        }
        if ($meta.completed_windows -le 0 -or $meta.input_samples -ne (8192L * $meta.completed_windows)) {
            throw ($test.name + ': sample/window count mismatch')
        }
        if ($test.seconds -eq 0) {
            $records = @(Get-Content -LiteralPath (Join-Path $out 'frequency.json') -Raw | ConvertFrom-Json)
            if ($records.Count -ne 4 -or $meta.input_samples -ne 32768) { throw 'Finite tone capture count mismatch' }
            foreach ($record in $records) {
                if ($record.peak_hz -ne 25000000 -or $record.rms_codes -ne 8192 -or $record.peak_codes -ne 8192) {
                    throw 'Finite tone frequency/amplitude mismatch'
                }
            }
        } elseif ($meta.input_samples -lt (0.95 * $test.seconds * 100000000)) {
            throw ($test.name + ': insufficient acquired samples for requested duration')
        }
        $results += [ordered]@{ name=$test.name; passed=$true; metadata=$meta; directory=$out }
        Write-Host ('PASS: ' + $test.name)
    }
    $summary = [ordered]@{ passed=$true; completed_at=(Get-Date).ToString('o');
        scope='UDP completeness, finite tone frequency/amplitude, 10s and 60s continuity, hardware latency counters';
        independent_clock_measurement=$false; tests=$results }
} catch {
    $summary = [ordered]@{ passed=$false; completed_at=(Get-Date).ToString('o'); error=$_.Exception.Message; tests=$results }
    throw
} finally {
    if ($null -ne $summary) { $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outRoot 'network_validation.json') -Encoding UTF8 }
    Write-Host ('Results: ' + $outRoot)
}
