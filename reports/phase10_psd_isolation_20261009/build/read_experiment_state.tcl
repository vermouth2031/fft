connect
targets -set -filter {name =~ "ARM*#0"}
puts "REBOOT_STATUS [mrd 0xf8000258]"
puts "FPGA0_CLK_CTRL [mrd 0xf8000170]"
puts "FPGA1_CLK_CTRL [mrd 0xf8000180]"
disconnect
