set root [file normalize [file join [file dirname [info script]] ..]]
create_project builder_test $root/build/builder_test -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/math_units.sv $root/rtl/result_builder.sv]
add_files -fileset sim_1 -norecurse $root/tests/tb_result_builder.sv
set_property top tb_result_builder [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/builder_test/builder_test.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "BUILDER_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Builder regression failed"}
close_project
