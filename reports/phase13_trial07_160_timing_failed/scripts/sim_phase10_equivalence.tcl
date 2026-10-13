set root [file normalize [file join [file dirname [info script]] ..]]
create_project phase10_equivalence $root/build/phase10_equivalence -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/iq_build_config.sv $root/rtl/spectrum_lane.sv $root/rtl/spectrum_store.sv $root/rtl/math_units.sv $root/rtl/spectrum_measure.sv]
add_files -fileset sim_1 -norecurse [list $root/tests/reference/phase9_spectrum_measure.sv $root/tests/tb_phase10_equivalence.sv]
set_property top tb_phase10_equivalence [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/phase10_equivalence/phase10_equivalence.sim/sim_1/behav/xsim/simulate.log r]
set text [read $f];close $f
if {[string first "PHASE10_EQUIVALENCE_PASS" $text]<0||[string first "Fatal:" $text]>=0} {error "Phase 9/10 cycle equivalence failed"}
close_project
