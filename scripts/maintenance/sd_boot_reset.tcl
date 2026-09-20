# Separate from writing so host SHA-256 must succeed before any SD boot.
if {$argc != 1 || [lindex $argv 0] ne "BOOT_FROM_SD"} {
    error "Usage: sd_boot_reset.tcl BOOT_FROM_SD"
}
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
# BOOT_MODE[2:0] must be SD (0b101), matching the FSBL BOOT_MODES_MASK.
set mode [expr {[lindex [mrd -value 0xf800025c 1] 0] & 7}]
if {$mode != 5} {error "Board boot mode is $mode, not SD; do not claim an SD boot"}
rst -system
puts "SD_SYSTEM_RESET_REQUESTED boot_mode=$mode"
disconnect
