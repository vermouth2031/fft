set root D:/fft/fft_phase10_resource_opt
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
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000240 0xf
ps7_init
fpga -file $root/artifacts/iq_analyzer.bit
ps7_post_config
rst -processor -stop
dow $root/artifacts/iq_udp.elf
mwr 0xf8000258 0x5a000000
con
puts "CLEAN_RESET_CANDIDATE_READY"
disconnect
