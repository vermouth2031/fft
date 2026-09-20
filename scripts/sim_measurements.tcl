set root [file normalize [file join [file dirname [info script]] ..]]
create_project measurements $root/build/measurements -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/math_units.sv $root/rtl/time_measure.sv $root/rtl/digital_burst_measure.sv $root/rtl/spectrum_measure.sv]
add_files -fileset sim_1 -norecurse [list $root/tests/tb_measurements.sv $root/tests/tb_burst_edges.sv $root/data/test_iq.mem $root/data/time_expected.mem $root/data/time_counts.mem $root/data/spectrum_input.mem $root/data/spectrum_expected.mem]
set_property top tb_measurements [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/measurements/measurements.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "MEASUREMENTS_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Measurement regression failed"}
set_property top tb_burst_edges [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/measurements/measurements.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "BURST_EDGES_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Burst edge regression failed"}
close_project
