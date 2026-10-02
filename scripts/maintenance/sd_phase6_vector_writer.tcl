if {$argc != 6 || [lindex $argv 5] ne "WRITE_PHASE6_VECTOR"} {
    error "Usage: sd_phase6_vector_writer.tcl ELF VECTOR PS7_INIT CONTROL OUTPUT WRITE_PHASE6_VECTOR"
}
lassign $argv maintenance_elf vector ps7_script control_file output_dir interlock
foreach required [list $maintenance_elf $vector $ps7_script $control_file] {
    if {![file isfile $required]} {error "Required file missing: $required"}
}
set image_size [file size $vector]
if {$image_size <= 0 || $image_size > 0x100000 || ($image_size % 4) != 0 || [file size $control_file] != 64} {
    error "Invalid vector/control size"
}
file mkdir $output_dir
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
rst -system -stop
after 1000
targets -set -filter {name =~ "ARM*#0"}
source $ps7_script
ps7_init
ps7_post_config
rst -processor -stop
dow $maintenance_elf
dow -data $vector 0x10000000
verify -data $vector 0x10000000
dow -data $control_file 0x0ff00000
verify -data $control_file 0x0ff00000
con
set finished 0
for {set poll 0} {$poll < 720} {incr poll} {
    after 250
    set status [lindex [mrd -value 0x0ff00014 1] 0]
    if {$status == 2 || ($status & 0x80000000) != 0} {set finished 1;break}
}
if {!$finished} {error "Vector maintenance timed out; CPU left running"}
stop
mrd -size b -bin -file [file join $output_dir mailbox.bin] 0x0ff00000 64
if {$status != 2} {error "Vector maintenance failed; inspect mailbox.bin"}
mrd -bin -file [file join $output_dir vector_readback.bin] 0x12000000 [expr {$image_size / 4}]
puts "SD_VECTOR_READBACK_EXPORTED bytes=$image_size"
disconnect
