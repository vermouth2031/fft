# Diagnostic RAM/JTAG image. Firmware is the unchanged verified Phase 9 ELF.
set root D:/fft/fft_phase10_isolate_psd
set baseline D:/fft/fft_phase9_fft16k
foreach f [list $root/artifacts/iq_analyzer.bit $baseline/artifacts/ps7_init.tcl $baseline/artifacts/iq_udp.elf] {
 if {![file exists $f]} {error "Missing diagnostic artifact: $f"}
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
source $baseline/artifacts/ps7_init.tcl
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000240 0xf
ps7_init
fpga -file $root/artifacts/iq_analyzer.bit
ps7_post_config
rst -processor -stop
dow $baseline/artifacts/iq_udp.elf
mwr 0xf8000258 0x5a000000
con
puts "ISOLATE_PSD_PHASE9_FIRMWARE_RAM_READY"
disconnect
