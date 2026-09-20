set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint $root/build/board/iq_board.runs/impl_1/system_wrapper_placed.dcp
file mkdir $root/build/diagnostics
report_timing -max_paths 30 -path_type full_clock_expanded -file $root/build/diagnostics/placed_timing_paths.rpt
report_timing -from [get_clocks clk_fpga_1] -to [get_clocks clk_fpga_1] -max_paths 5 -file $root/build/diagnostics/core_timing_paths.rpt
report_utilization -hierarchical -file $root/build/diagnostics/placed_utilization.rpt
puts "CLOCKS [get_clocks]"
foreach p [get_timing_paths -max_paths 12 -nworst 2] {
 puts "PATH: [get_property STARTPOINT_PIN $p] -> [get_property ENDPOINT_PIN $p] SLACK=[get_property SLACK $p] REQUIREMENT=[get_property REQUIREMENT $p]"
}
foreach p [get_timing_paths -from [get_clocks clk_fpga_1] -to [get_clocks clk_fpga_1] -max_paths 5] {
 puts "CORE_PATH: [get_property STARTPOINT_PIN $p] -> [get_property ENDPOINT_PIN $p] SLACK=[get_property SLACK $p]"
}
close_design
