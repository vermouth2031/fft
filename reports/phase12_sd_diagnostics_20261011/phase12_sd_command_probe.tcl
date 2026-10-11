connect
targets -set -filter {name =~ "ARM*#0"}
puts "SD_TRANSFER_COMMAND [mrd 0xe010000c 1]"
puts "SD_RESPONSES [mrd 0xe0100010 4]"
puts "SD_STATUS [mrd 0xe0100030 1]"
puts "SD_ARGUMENT [mrd 0xe0100008 1]"
disconnect
