connect
targets -set -filter {name =~ "ARM*#0"}
puts "STATE [state]"
puts "RESET [mrd 0xf8000258]"
puts "DMA [mrd -force 0x40400000 12]"
puts "LOADER [mrd -force 0x400001c0 10]"
puts "HP0 [mrd 0xf8008000 12]"
disconnect
