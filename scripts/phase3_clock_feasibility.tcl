# Constraint-only feasibility probe. Never emits a bitstream or changes the board.
if {$argc != 2} {error "Usage: checkpoint output_directory"}
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
file mkdir $output
set_param general.maxThreads 4
open_checkpoint $checkpoint
report_clocks -file $output/clocks.rpt
set f [open $output/same_clock_budget.csv w]
puts $f "clock,current_period_ns,current_setup_slack_ns,source125_period_ns,source125_fixed_route_slack_estimate_ns,both_scaled_period_ns,both_scaled_fixed_route_slack_estimate_ns"
foreach clock [get_clocks] {
    set period [get_property PERIOD $clock]
    set paths [get_timing_paths -from $clock -to $clock -delay_type max -max_paths 1]
    if {[llength $paths]==0} {continue}
    set slack [get_property SLACK [lindex $paths 0]]
    set source_period $period
    if {abs($period-10.0)<0.001} {set source_period 8.0}
    set scaled [expr {$period*0.8}]
    puts $f "$clock,$period,$slack,$source_period,[expr {$slack+$source_period-$period}],$scaled,[expr {$slack+$scaled-$period}]"
    report_timing -from $clock -to $clock -delay_type max -max_paths 5 -file $output/${clock}_worst.rpt
}
close $f
set f [open $output/SCOPE.txt w]
puts $f "Fixed routed netlist, same-clock setup budget arithmetic only. Clock routing, uncertainty, CDC and hardware clocks are unchanged. This is neither a rerouted 125MSPS implementation nor throughput/board acceptance. Negative estimates reject directly reusing this implementation at the proposed period; a redesigned implementation could differ."
close $f
close_design
