set root [file normalize [file join [file dirname [info script]] ..]]
create_project phase11_window $root/build/phase11_window -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/iq_build_config.sv $root/rtl/window_fft.sv $root/tests/reference/phase10_window_fft.sv $root/data/hann_quarter_u18_f17.mem]
add_files -fileset sim_1 -norecurse $root/tests/tb_phase11_window.sv
set_property top tb_phase11_window [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/phase11_window/phase11_window.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "PHASE11_WINDOW_EQUIVALENCE_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Window equivalence failed"}
close_project
