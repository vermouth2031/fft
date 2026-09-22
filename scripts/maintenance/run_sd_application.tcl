# Run the actual, unmodified iq_sd.elf. It creates a fresh RUNxxxx directory.
# A source-line hardware breakpoint after all f_close/f_mount operations
# replaces dependence on UART or a guessed delay.
if {$argc != 5} {error "Usage: run_sd_application.tcl BIT SD_ELF PS7_INIT COMPILED_SOURCE COMPLETION_LINE"}
lassign $argv bitstream application ps7_script compiled_source completion_line
foreach path [list $bitstream $application $ps7_script $compiled_source] {
    if {![file isfile $path]} {error "Missing input: $path"}
}
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
puts "SD_VALIDATION_SYSTEM_RESET purpose=actual_sd_application"
rst -system -stop
after 1000
targets -set -filter {name =~ "ARM*#0"}
fpga -file $bitstream
source $ps7_script
ps7_init
ps7_post_config
# Enter the standalone ELF from reset processor state, not a prior exception.
rst -processor -stop
puts "JTAG_PROCESSOR_RESET_BEFORE_ELF"
dow $application
set completion [bpadd -file $compiled_source -line $completion_line -type hw]
puts "SD_APPLICATION_COMPLETION_BREAKPOINT $completion source=$compiled_source line=$completion_line"
con -block -timeout 120
puts "SD_APPLICATION_STOP_CONTEXT [bt]"
puts "SD_APPLICATION_STOP_PC [rrd pc]"
bpremove $completion
puts "SD_APPLICATION_REACHED_COMPLETION_LINE"
disconnect
