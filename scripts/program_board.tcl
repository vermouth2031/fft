# RAM-only programming; does not write QSPI or an SD card.
set root [file normalize [file join [file dirname [info script]] ..]]
foreach f {iq_analyzer.bit iq_udp.elf ps7_init.tcl} {
 if {![file exists $root/artifacts/$f]} {error "Missing artifact: $f. Run the build first."}
}
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
rst -system
after 3000
targets -set -filter {name =~ "ARM*#1"}
stop
targets -set -filter {name =~ "ARM*#0"}
stop
bpremove -all
source $root/artifacts/ps7_init.tcl
# Hold PL interfaces in reset while PS clocks/DDR and the new PL image load.
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000240 0xf
ps7_init
fpga -file $root/artifacts/iq_analyzer.bit
ps7_post_config
# Enter the standalone ELF from reset processor state, not a prior exception.
rst -processor -stop
puts "JTAG_PROCESSOR_RESET_BEFORE_ELF"
dow $root/artifacts/iq_udp.elf
puts "REBOOT_STATUS_BEFORE_MARKER [mrd 0xf8000258]"
mwr 0xf8000258 0x5a000000
puts "REBOOT_STATUS_MARKER [mrd 0xf8000258]"
con
puts "Firmware started. UART 115200 8N1; board IP 192.168.1.10; UDP port 5001."
disconnect
