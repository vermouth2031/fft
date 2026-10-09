source D:/fft/fft_phase10_resource_opt/build/program_clean_reset.tcl
connect
targets -set -filter {name =~ "ARM*#0"}
stop
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000240 0xf
mwr -force 0xf8000170 0x00200800
mwr -force 0xf8000180 0x00200800
after 10
mwr -force 0xf8000240 0
mwr -force 0xf8000004 0x767b
rst -processor -stop
dow D:/fft/fft_phase10_resource_opt/artifacts/iq_udp.elf
puts "DIAGNOSTIC_ONLY_BOTH_62_5MHZ [mrd 0xf8000170 5]"
con
disconnect
