# RAM-only programming; does not write QSPI or an SD card.
set root [file normalize [file join [file dirname [info script]] ..]]
foreach f {iq_analyzer.bit iq_udp.elf ps7_init.tcl} {
 if {![file exists $root/artifacts/$f]} {error "Missing artifact: $f. Run the build first."}
}
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
rst -system
after 3000
targets -set -filter {name =~ "ARM*#0"}
stop
fpga -file $root/artifacts/iq_analyzer.bit
source $root/artifacts/ps7_init.tcl
ps7_init
ps7_post_config
# Enter the standalone ELF from reset processor state, not a prior exception.
rst -processor -stop
puts "JTAG_PROCESSOR_RESET_BEFORE_ELF"
dow $root/artifacts/iq_udp.elf
con
puts "Firmware started. UART 115200 8N1; board IP 192.168.1.10; UDP port 5001."
