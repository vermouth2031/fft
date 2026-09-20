set root [file normalize [file join [file dirname [info script]] ..]]
set_param general.maxThreads 4
set_param board.repoPaths [list $root/vendor/boards]
open_project $root/build/board/iq_board.xpr
add_files -norecurse [glob $root/rtl/*.sv]
add_files -fileset constrs_1 -norecurse $root/constraints/cdc.xdc
set_property used_in_synthesis false [get_files cdc.xdc]
open_bd_design [get_files system.bd]
update_compile_order -fileset sources_1
update_module_reference -verbose [get_ips system_iq_0_0]
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
update_compile_order -fileset sources_1
set iq_run [get_runs -quiet system_iq_0_0_synth_1]
if {[llength $iq_run]} {reset_run $iq_run}
reset_run synth_1
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]]!="100%"} {error "Synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]]!="100%"} {error "Implementation failed"}
source $root/scripts/finish_board.tcl
