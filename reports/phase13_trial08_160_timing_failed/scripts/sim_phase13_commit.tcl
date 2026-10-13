set root [file normalize [file join [file dirname [info script]] ..]]
create_project commit_test $root/build/commit_test -part xc7z020clg400-1 -force
add_files -norecurse [list $root/rtl/iq_dma_commit.sv $root/rtl/iq_bank_metadata.sv]
add_files -fileset sim_1 -norecurse $root/tests/tb_phase13_commit.sv
set_property top tb_phase13_commit [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/commit_test/commit_test.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f];close $f
if {[string first "PHASE13_COMMIT_PASS" $log]<0||[string first "Fatal:" $log]>=0} {error "Commit regression failed"}
close_project
