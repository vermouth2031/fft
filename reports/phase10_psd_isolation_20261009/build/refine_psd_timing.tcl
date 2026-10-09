# Physical-only diagnostic refinement; preserves all clocks and timing constraints.
set root D:/fft/fft_phase10_isolate_psd
set_param general.maxThreads 4
open_project $root/build/board/iq_board.xpr
open_run impl_1
report_timing -max_paths 10 -file $root/build/logs/psd_before_refine.rpt
phys_opt_design -directive Explore
set slack [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
puts "PSD_REFINE_EXPLORE_WNS=$slack"
if {$slack < 0} {
 set enable [get_nets -quiet system_i/iq_0/inst/freq_ring_n_148]
 if {[llength $enable] == 1} {phys_opt_design -force_replication_on_nets $enable}
}
set slack [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
puts "PSD_REFINE_FINAL_WNS=$slack"
report_timing -max_paths 10 -file $root/build/logs/psd_after_refine.rpt
write_checkpoint -force $root/build/board/psd_refined.dcp
if {$slack < 0} {error "Refinement did not close setup timing; no artifact promoted"}
write_bitstream -force $root/build/board/iq_board.runs/impl_1/system_wrapper.bit
# Run the canonical full timing/CDC/DRC gates against this in-memory design.
set f [open $root/scripts/finish_board.tcl r]
set finish [read $f]
close $f
regsub {^open_run impl_1\r?\n} $finish {} finish
eval $finish
