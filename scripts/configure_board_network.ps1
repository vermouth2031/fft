param([switch]$Restore)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$reportPath = Join-Path $root 'reports\network_adapter_setup.json'
$backupPath = Join-Path $root 'reports\network_adapter_before.json'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator rights required. Run this script through Windows UAC.'
}
try {
    $adapter = @(Get-NetAdapter | Where-Object { $_.InterfaceGuid -eq '{E685DD6F-F3DC-4262-A662-E682DEBA6D43}' })
    if ($adapter.Count -ne 1 -or $adapter[0].MacAddress -ne 'C4-C6-E6-8B-15-BF') { throw 'Expected wired adapter not found' }
    $index = $adapter[0].ifIndex
    $addresses = @(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore PersistentStore)
    $unexpected = @($addresses | Where-Object { $_.IPAddress -notin @('192.168.2.1','192.168.1.20') })
    if ($unexpected.Count) { throw 'Unexpected IPv4 address: inspect before changing this adapter' }
    $gateways = @(Get-NetRoute -InterfaceIndex $index -AddressFamily IPv4 | Where-Object DestinationPrefix -eq '0.0.0.0/0')
    if ($gateways.Count) { throw 'Unexpected gateway on the wired adapter' }
    if (-not (Test-Path -LiteralPath $backupPath)) {
        [ordered]@{
            saved_at = (Get-Date).ToString('o')
            adapter = $adapter[0] | Select-Object Name,InterfaceDescription,InterfaceGuid,MacAddress,ifIndex
            ipv4 = @($addresses | Select-Object IPAddress,PrefixLength,PrefixOrigin)
            dns = @((Get-DnsClientServerAddress -InterfaceIndex $index -AddressFamily IPv4).ServerAddresses)
            dhcp = [string](Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4).Dhcp
        } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $backupPath -Encoding UTF8
    }
    $target = if ($Restore) { '192.168.2.1' } else { '192.168.1.20' }
    $other = if ($Restore) { '192.168.1.20' } else { '192.168.2.1' }
    # Add the new address before removing the original, so a failure leaves a usable configuration.
    if (-not ($addresses | Where-Object IPAddress -eq $target)) {
        New-NetIPAddress -InterfaceIndex $index -IPAddress $target -PrefixLength 24 -AddressFamily IPv4 | Out-Null
    }
    if ($addresses | Where-Object IPAddress -eq $other) {
        Remove-NetIPAddress -InterfaceIndex $index -IPAddress $other -Confirm:$false
    }
    $actual = @(Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -PolicyStore PersistentStore | Select-Object IPAddress,PrefixLength)
    if ($actual.Count -ne 1 -or $actual[0].IPAddress -ne $target -or $actual[0].PrefixLength -ne 24) { throw 'IPv4 verification failed' }
    [ordered]@{
        configured_at = (Get-Date).ToString('o'); success = $true; restored = [bool]$Restore
        adapter_guid = [string]$adapter[0].InterfaceGuid; interface_index = $index
        ipv4 = $actual; gateway = $null; wifi_modified = $false; firewall_modified = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
} catch {
    [ordered]@{ attempted_at=(Get-Date).ToString('o'); success=$false; error=$_.Exception.Message } |
        ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
    throw
}
