source D:/fft/fft_phase10_resource_opt/scripts/program_board.tcl
targets -set -filter {name =~ "ARM*#0"}
mwr 0xf8000258 0x5a000000
bpadd -addr 0x100660 -type hw
puts "DMA_ERROR_BREAKPOINT_ARMED"
for {set i 0} {$i < 120} {incr i} {
 after 500
 set state [state]
 if {$state ne "Running"} {
  puts "CPU_STATE $state"
  puts "REGISTERS [rrd]"
  puts "RESET [mrd 0xf8000258]"
  puts "DMA [mrd 0x40400000 12]"
  puts "LOADER [mrd 0x400001c0 10]"
  break
 }
}
puts "END_STATE [state]"
bpremove -all
con
disconnect
