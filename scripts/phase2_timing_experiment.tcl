# Isolated physical optimization of a copy loaded from the frozen checkpoint.
# No constraints, RTL or generated vendor IP files are edited.
if {$argc != 3} {error "Usage: checkpoint output_directory directive"}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
set directive [lindex $argv 2]
if {[file exists $output]} {error "Refuse to overwrite an existing experiment"}
file mkdir $output
open_checkpoint $checkpoint
set f [open $output/commands.txt w]
puts $f "Vivado [version -short]"
puts $f "open_checkpoint $checkpoint"
puts $f "phys_opt_design -directive $directive"
puts $f "route_design -directive Explore"
close $f
report_timing_summary -delay_type min_max -report_unconstrained -file $output/before_timing.rpt
report_timing -max_paths 20 -path_type full_clock_expanded -file $output/before_paths.rpt
report_high_fanout_nets -max_nets 20 -file $output/high_fanout.rpt
set f [open $output/path_properties.txt w]
foreach path [get_timing_paths -max_paths 10 -nworst 2] {
 puts $f "[get_property STARTPOINT_PIN $path] -> [get_property ENDPOINT_PIN $path] SLACK=[get_property SLACK $path]"
}
close $f
phys_opt_design -directive $directive
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
puts $f "\{\"setup_slack_ns\":$setup,\"hold_slack_ns\":$hold,\"directive\":\"$directive\",\"board_tested\":false,\"promoted\":false\}"
close $f
puts "PHASE2_TIMING_EXPERIMENT_COMPLETE setup=$setup hold=$hold"
close_design
