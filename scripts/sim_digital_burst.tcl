set root [file normalize [file join [file dirname [info script]] ..]]
create_project digital_burst $root/build/digital_burst -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/time_measure.sv $root/rtl/digital_burst_measure.sv]
add_files -fileset sim_1 -norecurse [list $root/tests/tb_digital_burst.sv $root/build/digital_burst_vectors/digital_cases.txt]
set_property file_type {Memory Initialization Files} [get_files digital_cases.txt]
set_property top tb_digital_burst [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/digital_burst/digital_burst.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "DIGITAL_BURST_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Digital burst regression failed"}
close_project
