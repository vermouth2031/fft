connect
targets -set -filter {name =~ "ARM*#0"}
puts "SD_PRESENT_STATE [mrd -value 0xe0100024 1]"
puts "SD_HOST_POWER_CLOCK [mrd -value 0xe0100028 3]"
puts "SD_SLCR_CLOCK [mrd -value 0xf8000150 1]"
puts "SD_MIO_CONFIG [mrd -value 0xf80007a0 8]"
puts "GPIO_BANK1_INPUT [mrd -value 0xe000a064 1]"
puts "WRITER_MAILBOX [mrd -value 0x0ff00000 16]"
disconnect
