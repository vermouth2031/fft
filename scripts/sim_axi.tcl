set root [file normalize [file join [file dirname [info script]] ..]]
create_project axi_test $root/build/axi_test -part xc7z020clg400-1 -force
set_property simulator_language Mixed [current_project]
add_files -norecurse [glob $root/rtl/*.sv]
add_files -norecurse $root/data/hann_u18_f17.mem
read_ip $root/build/vivado/iq_analyzer.srcs/sources_1/ip/fft8192/fft8192.xci
add_files -fileset sim_1 -norecurse $root/tests/tb_axi.sv
set_property top tb_axi [get_filesets sim_1]
set_property top iq_peripheral [get_filesets sources_1]
set_property xsim.simulate.runtime {all} [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
update_compile_order -fileset sim_1
launch_simulation
close_sim
set f [open $root/build/axi_test/axi_test.sim/sim_1/behav/xsim/simulate.log r]
set log [read $f]
close $f
if {[string first "AXI_PASS" $log]<0 || [string first "Fatal:" $log]>=0} {error "AXI regression failed; inspect simulate.log"}
close_project
