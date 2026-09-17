open_run impl_1
file mkdir $root/reports
report_timing_summary -delay_type min_max -report_unconstrained -file $root/reports/timing_summary.rpt
report_utilization -hierarchical -file $root/reports/utilization.rpt
report_utilization -file $root/reports/utilization_flat.rpt
report_drc -file $root/reports/drc.rpt
report_cdc -details -file $root/reports/cdc.rpt
report_clock_interaction -file $root/reports/clock_interaction.rpt
report_bus_skew -file $root/reports/bus_skew.rpt
report_timing -max_paths 20 -file $root/reports/worst_paths.rpt
report_methodology -file $root/reports/methodology.rpt
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
puts "FINAL_SETUP_SLACK_NS=$wns HOLD_SLACK_NS=$whs"
if {$wns<0||$whs<0} {error "Timing FAILED. See reports; artifacts not promoted."}
set f [open $root/reports/timing_summary.rpt r];set timing [read $f];close $f
foreach check {no_clock unconstrained_internal_endpoints no_input_delay no_output_delay} {
 if {![regexp "checking $check \\(0\\)" $timing]} {error "Timing coverage failed: $check"}
}
set f [open $root/reports/cdc.rpt r];set cdc [read $f];close $f
if {[regexp {CDC-[0-9]+[ ]+Critical} $cdc]} {error "Unresolved critical CDC paths; inspect cdc.rpt"}
set f [open $root/reports/bus_skew.rpt r];set skew [read $f];close $f
if {[string first "VIOLATED" $skew]>=0} {error "Bus skew failed"}
foreach violation [get_drc_violations -quiet] {
 if {[get_property SEVERITY $violation] in {Error {Critical Warning}}} {error "DRC failure: $violation"}
}
file mkdir $root/artifacts
write_hw_platform -fixed -include_bit -force -file $root/artifacts/iq_analyzer.xsa
file copy -force $root/build/board/iq_board.runs/impl_1/system_wrapper.bit $root/artifacts/iq_analyzer.bit
set f [open $root/reports/hardware_validation.json w]
puts $f "\{\"status\":\"PASS\",\"setup_slack_ns\":$wns,\"hold_slack_ns\":$whs,\"cdc_critical\":0,\"unconstrained_internal_endpoints\":0,\"board_tested\":false,\"tool\":\"[version -short]\"\}"
close $f
close_project
