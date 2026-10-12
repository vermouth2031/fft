set root [file normalize [file join [file dirname [info script]] ..]]
create_project phase12_time_equivalence $root/build/phase12_time_equivalence -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/iq_build_config.sv $root/rtl/time_measure.sv $root/rtl/digital_burst_measure.sv]
add_files -fileset sim_1 -norecurse [list $root/tests/reference/phase11_time_measure.sv $root/tests/tb_phase12_time_equivalence.sv]
set_property top tb_phase12_time_equivalence [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/phase12_time_equivalence/phase12_time_equivalence.sim/sim_1/behav/xsim/simulate.log r]
set text [read $f];close $f
if {[string first "PHASE12_TIME_EQUIVALENCE_PASS" $text]<0||[string first "Fatal:" $text]>=0} {error "Phase 11/12 time equivalence failed"}
close_project
