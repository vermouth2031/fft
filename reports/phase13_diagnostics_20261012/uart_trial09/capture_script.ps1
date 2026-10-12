$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'D:/fft/fft_phase13_structure_opt'
$outputRoot='reports/phase13_diagnostics_20261012/uart_trial09'
$stopFile='build/phase13_uart_trial09.stop'
if((Test-Path $outputRoot) -or (Test-Path $stopFile)){throw 'Preserve earlier UART capture'}
New-Item -ItemType Directory -Path $outputRoot | Out-Null
Copy-Item -LiteralPath $PSCommandPath -Destination "$outputRoot/capture_script.ps1"
$port=[System.IO.Ports.SerialPort]::new('COM4',115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$port.Handshake=[System.IO.Ports.Handshake]::None
$port.DtrEnable=$false
$port.RtsEnable=$false
$port.ReadTimeout=200
$raw=[System.IO.File]::Create([IO.Path]::GetFullPath("$outputRoot/uart.bin"))
$transcript=[System.IO.StreamWriter]::new([IO.Path]::GetFullPath("$outputRoot/uart.txt"),$false,[Text.UTF8Encoding]::new($false))
$transcript.AutoFlush=$true
$metadata=[ordered]@{started_at=(Get-Date).ToString('o');port='COM4';baud=115200;ftdi_device='VID_0403+PID_6010+210351A82208B';dtr=$false;rts=$false;serial_bytes_written=0;scope='Passive UART receive only; no commands, reset or programming';status='STARTING';received_bytes=0}
try {
    $port.Open()
    $metadata.status='RECEIVING'
    $metadata | ConvertTo-Json | Set-Content -LiteralPath "$outputRoot/capture.json" -Encoding utf8
    Write-Output 'UART_MONITOR_READY COM4 115200 RECEIVE_ONLY'
    $deadline=(Get-Date).AddMinutes(90)
    while((Get-Date) -lt $deadline -and -not(Test-Path $stopFile)) {
        $available=$port.BytesToRead
        if($available -gt 0) {
            $buffer=[byte[]]::new($available)
            $count=$port.Read($buffer,0,$available)
            $raw.Write($buffer,0,$count);$raw.Flush()
            $metadata.received_bytes+=$count
            $transcript.WriteLine('['+(Get-Date).ToString('o')+'] '+[Text.Encoding]::ASCII.GetString($buffer,0,$count))
        } else {Start-Sleep -Milliseconds 100}
    }
    $metadata.status='CAPTURE_FINISHED'
} catch {
    $metadata.status='CAPTURE_STOPPED_ON_ERROR';$metadata.error=$_.Exception.Message
    $transcript.WriteLine('['+(Get-Date).ToString('o')+'] CAPTURE_ERROR '+$_.Exception.Message)
    throw
} finally {
    $metadata.finished_at=(Get-Date).ToString('o')
    $metadata | ConvertTo-Json | Set-Content -LiteralPath "$outputRoot/capture.json" -Encoding utf8
    $port.Dispose();$raw.Dispose();$transcript.Dispose()
}
Write-Output ('UART_CAPTURE_COMPLETE bytes='+$metadata.received_bytes)
