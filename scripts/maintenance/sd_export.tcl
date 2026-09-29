# Read-only helper execution. Each call contains exactly one system reset.
if {$argc != 4} {error "Usage: sd_export.tcl HELPER_ELF PS7_INIT CONTROL_BIN OUTPUT_DIR"}
lassign $argv helper_elf ps7_script control_file output_dir
foreach path [list $helper_elf $ps7_script $control_file] {
    if {![file isfile $path]} {error "Missing input: $path"}
}
if {[file size $control_file] != 64} {error "Invalid SD export mailbox"}
file mkdir $output_dir
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
puts "SD_VALIDATION_SYSTEM_RESET purpose=read_only_export"
rst -system -stop
after 1000
targets -set -filter {name =~ "ARM*#0"}
source $ps7_script
ps7_init
ps7_post_config
# Enter the standalone ELF from reset processor state, not a prior exception.
rst -processor -stop
puts "JTAG_PROCESSOR_RESET_BEFORE_ELF"
dow $helper_elf
dow -data $control_file 0x0ff00000
verify -data $control_file 0x0ff00000
con
set done 0
for {set n 0} {$n < 480} {incr n} {
    after 250
    set status [lindex [mrd -value 0x0ff0000c 1] 0]
    if {$status == 2 || ($status & 0x80000000) != 0} {set done 1;break}
}
if {!$done} {error "Read-only export timeout; inspect target before another reset"}
stop
mrd -size b -bin -file [file join $output_dir mailbox.bin] 0x0ff00000 64
if {$status != 2} {error "SD export failed; mailbox stage/error/index identify the missing or invalid file"}
set count [lindex [mrd -value 0x0ff00018 1] 0]
if {$count < 16 || $count > 0x1000000} {error "Invalid archive size"}
mrd -size b -bin -file [file join $output_dir files.sdx] 0x12000000 $count
puts "SD_READ_ONLY_EXPORT_PASS bytes=$count"
disconnect
