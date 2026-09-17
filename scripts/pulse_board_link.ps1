param([string]$Directory = 'D:\fft\iq_analyzer\captures\extended_20260917\link_interrupt_fixed')
$ErrorActionPreference = 'Stop'
$directory = $Directory
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$adapter = @(Get-NetAdapter | Where-Object InterfaceGuid -eq '{E685DD6F-F3DC-4262-A662-E682DEBA6D43}')
if ($adapter.Count -ne 1 -or $adapter[0].MacAddress -ne 'C4-C6-E6-8B-15-BF') { throw 'Wrong adapter' }
$events = @()
Set-Content -LiteralPath (Join-Path $directory 'ready.txt') -Value 'Waiting for capture trigger'
$deadline = (Get-Date).AddSeconds(45)
while (-not (Test-Path -LiteralPath (Join-Path $directory 'trigger.txt'))) {
    if ((Get-Date) -gt $deadline) { throw 'No trigger; adapter was not changed' }
    Start-Sleep -Milliseconds 100
}
try {
    $events += @{event='disable_requested';time=(Get-Date).ToString('o')}
    $adapter[0] | Disable-NetAdapter -Confirm:$false
    $events += @{event='disabled';time=(Get-Date).ToString('o');status=[string](Get-NetAdapter -InterfaceIndex $adapter[0].ifIndex).Status}
    Start-Sleep -Seconds 3
} finally {
    $adapter[0] | Enable-NetAdapter -Confirm:$false
    $events += @{event='enabled';time=(Get-Date).ToString('o')}
    $events | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'adapter_events.json') -Encoding UTF8
}
