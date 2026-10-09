source D:/fft/fft_phase10_resource_opt/build/program_clean_reset.tcl
connect
targets -set -filter {name =~ "ARM*#0"}
stop
set address [lindex $argv 0]
if {$address eq ""} {set address 0x01000000}
dow -data D:/fft/fft_phase10_resource_opt/build/phase10_dma_debug.bin $address
mwr -force 0x400001c4 0
mwr -force 0x400001c8 0x4000
mwr -force 0x400001cc 1
mwr -force 0x400001d0 0xc8f64def
mwr -force 0x400001c0 5
mwr -force 0x40400000 4
after 10
mwr -force 0x40400000 1
mwr -force 0x40400018 $address
mwr -force 0x40400028 0x10000
after 100
puts "SOURCE $address"
puts "DMA [mrd -force 0x40400000 12]"
puts "LOADER [mrd -force 0x400001c0 10]"
puts "RESET [mrd 0xf8000258]"
disconnect
