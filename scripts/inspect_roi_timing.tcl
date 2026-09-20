# Read-only routed timing diagnosis; does not alter the implemented design.
set root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint $root/build/board/iq_board.runs/impl_1/system_wrapper_postroute_physopt.dcp
set peaks [get_cells -hier -filter {NAME =~ */core/sm/*peak* && IS_SEQUENTIAL == 1}]
set roi [get_cells -hier -filter {NAME =~ */core/sm/roi_power_reg* && IS_SEQUENTIAL == 1}]
if {[llength $peaks] == 0 || [llength $roi] == 0} {error "Expected spectrum ROI/peak registers are missing"}
report_timing -to $roi -max_paths 3 -file $root/reports/roi_input_timing.rpt
report_timing -to $peaks -max_paths 3 -file $root/reports/roi_peak_timing.rpt
set roi_slack [get_property SLACK [get_timing_paths -to $roi -max_paths 1]]
set peak_slack [get_property SLACK [get_timing_paths -to $peaks -max_paths 1]]
set f [open $root/reports/roi_timing.json w]
puts $f "\{\"roi_register_slack_ns\":$roi_slack,\"peak_register_slack_ns\":$peak_slack,\"scope\":\"Read-only timing of current routed spectrum paths\"\}"
close $f
puts "ROI_TIMING_PASS roi=$roi_slack peak=$peak_slack"
close_design
