set root [file normalize [file join [file dirname [info script]] ..]]
open_project $root/build/vivado/iq_analyzer.xpr
add_files -norecurse [glob $root/rtl/*.sv]
add_files -norecurse $root/data/hann_u18_f17.mem
add_files -fileset sim_1 -norecurse [list $root/tests/tb_core.sv $root/data/test_iq.mem $root/data/golden_fft.mem]
set_property top tb_core [get_filesets sim_1]
set_property top analyzer_core [get_filesets sources_1]
set_property xsim.simulate.runtime {all} [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
launch_simulation
close_sim
set f [open $root/build/vivado/iq_analyzer.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f]
close $f
if {[string first "CORE_PASS" $log]<0 || [string first "Fatal:" $log]>=0} {error "Core regression failed; inspect simulate.log"}
close_project
