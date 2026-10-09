connect
targets -set -filter {name =~ "ARM*#0"}
puts "REBOOT_STATUS [mrd 0xf8000258]"
puts "FCLK0_AND_FCLK1 [mrd 0xf8000170 5]"
disconnect
