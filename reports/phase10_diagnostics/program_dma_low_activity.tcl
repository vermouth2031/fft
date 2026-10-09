source D:/fft/fft_phase10_resource_opt/build/program_clean_reset.tcl
connect
targets -set -filter {name =~ "ARM*#0"}
stop
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000180 0x00200800
mwr -force 0xf8000004 0x767b
puts "DIAGNOSTIC_ONLY_FFT_62_5MHZ [mrd 0xf8000180]"
con
disconnect
