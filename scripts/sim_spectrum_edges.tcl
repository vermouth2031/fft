set root [file normalize [file join [file dirname [info script]] ..]]
create_project spectrum_edges $root/build/spectrum_edges_unified -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/math_units.sv $root/rtl/spectrum_measure.sv]
add_files -fileset sim_1 -norecurse $root/tests/tb_spectrum_edges.sv
set_property top tb_spectrum_edges [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/spectrum_edges_unified/spectrum_edges.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "SPECTRUM_EDGES_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Spectrum edge regression failed"}
close_project

