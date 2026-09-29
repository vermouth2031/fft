# Targeted tool-driven replication, always in an isolated checkpoint.
if {$argc != 2} {error "Usage: checkpoint new_output_directory"}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} {error "Refusing existing experiment directory"}
file mkdir $output
help phys_opt_design
open_checkpoint $checkpoint
set nets [get_nets -hier -filter {NAME =~ */axi_wrapper/ce_w2c}]
if {[llength $nets] != 1} {error "Expected one FFT ce_w2c net, got [llength $nets]"}
set f [open $output/identity.txt w]
puts $f "Vivado [version -short]\nCheckpoint $checkpoint\nNet $nets"
puts $f "Drivers [get_pins -of_objects $nets -filter {DIRECTION == OUT}]"
puts $f "Loads [llength [get_pins -of_objects $nets -filter {DIRECTION == IN}]]"
close $f
report_property $nets -file $output/net_properties.txt
report_timing_summary -delay_type min_max -report_unconstrained -file $output/before_timing.rpt
report_high_fanout_nets -max_nets 20 -file $output/before_fanout.rpt
phys_opt_design -force_replication_on_nets $nets
report_high_fanout_nets -max_nets 20 -file $output/after_replication_fanout.rpt
route_design -directive Explore
report_timing_summary -delay_type min_max -report_unconstrained -file $output/after_timing.rpt
report_timing -max_paths 20 -path_type full_clock_expanded -file $output/after_paths.rpt
report_utilization -file $output/utilization.rpt
report_cdc -details -file $output/cdc.rpt
report_drc -file $output/drc.rpt
report_bus_skew -file $output/bus_skew.rpt
write_checkpoint $output/candidate.dcp
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
set f [open $output/result.json w]
puts $f "\{\"setup_slack_ns\":$setup,\"hold_slack_ns\":$hold,\"board_tested\":false,\"promoted\":false\}"
close $f
puts "PHASE3_TIMING_COMPLETE setup=$setup hold=$hold"
close_design
