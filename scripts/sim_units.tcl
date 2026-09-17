set root [file normalize [file join [file dirname [info script]] ..]]
create_project unit_test $root/build/unit_test -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/math_units.sv $root/rtl/record_ring.sv]
add_files -fileset sim_1 -norecurse [list $root/tests/tb_units.sv $root/data/math_vectors.mem]
set_property top tb_units [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/unit_test/unit_test.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "UNITS_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Unit regression failed"}
close_project
