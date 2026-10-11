connect
targets -set -filter {name =~ "ARM*#0"}
set mode [expr {[lindex [mrd -value 0xf800025c 1] 0] & 7}]
puts "BOOT_MODE=$mode"
if {$mode != 5} {error "SD boot mode required"}
disconnect
