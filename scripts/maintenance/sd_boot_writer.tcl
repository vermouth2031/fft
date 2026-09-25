# Invoked only by sd_boot_update.py after build/board/provenance checks.
# The final argument is an explicit write interlock; there is no default run.
if {$argc != 6 || [lindex $argv 5] ne "WRITE_BOOT_BIN"} {
    error "Usage: sd_boot_writer.tcl ELF BOOT_UDP PS7_INIT CONTROL_BIN OUTPUT_DIR WRITE_BOOT_BIN"
}
lassign $argv maintenance_elf boot_image ps7_script control_file output_dir interlock
foreach required [list $maintenance_elf $boot_image $ps7_script $control_file] {
    if {![file isfile $required]} {error "Required file missing: $required"}
}
set image_size [file size $boot_image]
if {$image_size <= 0 || $image_size > 0x1000000 || ($image_size % 4) != 0 || [file size $control_file] != 64} {
    error "Invalid image/control size"
}
file mkdir $output_dir
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
# Halt at reset so an older SD application cannot run filesystem operations
# between reset and maintenance download.
rst -system -stop
after 1000
targets -set -filter {name =~ "ARM*#0"}
source $ps7_script
ps7_init
ps7_post_config
# Enter the standalone ELF from reset processor state, not a prior exception.
rst -processor -stop
puts "JTAG_PROCESSOR_RESET_BEFORE_ELF"
dow $maintenance_elf
dow -data $boot_image 0x10000000
verify -data $boot_image 0x10000000
dow -data $control_file 0x0ff00000
verify -data $control_file 0x0ff00000
con
set finished 0
for {set poll 0} {$poll < 720} {incr poll} {
    after 250
    set status [lindex [mrd -value 0x0ff00014 1] 0]
    if {$status == 2 || ($status & 0x80000000) != 0} {set finished 1;break}
}
if {!$finished} {
    # Leave the CPU running: halting in a filesystem update is unsafe.
    error "Maintenance timed out; CPU left running. Inspect mailbox before any reset."
}
stop
mrd -size b -bin -file [file join $output_dir mailbox.bin] 0x0ff00000 64
puts "SD_BOOT_MAILBOX [mrd -value 0x0ff00000 16]"
if {$status != 2} {error "Maintenance failed; see mailbox.bin and UART; no restart performed"}
mrd -bin -file [file join $output_dir sd_boot_readback.bin] 0x12000000 [expr {$image_size / 4}]
puts "SD_BOOT_READBACK_EXPORTED bytes=$image_size"
disconnect
