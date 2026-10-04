# Read-only GEM counters for separating Ethernet ingress, firmware RX, and TX loss.
connect
targets -set -filter {name =~ "ARM*#0"}
catch {stop}
foreach {name offset} {
    nwctrl 0x000
    nwsr 0x008
    gem_revision 0x0fc
    txsr 0x014
    rxqbase 0x018
    txqbase 0x01c
    rxsr 0x020
    tx_frames 0x108
    tx_underruns 0x134
    rx_frames 0x158
    rx_fcs_errors 0x190
    rx_resource_errors 0x1a0
    rx_overruns 0x1a4
    rx_udp_checksum_errors 0x1b0
} {
    puts [format "GEM_%s=0x%08X" [string toupper $name] [mrd -value [expr {0xE000B000 + $offset}]]]
}
con
exit
