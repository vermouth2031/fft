set root [file normalize [file join [file dirname [info script]] ..]]
set_param general.maxThreads 1
set_param board.repoPaths [list $root/vendor/boards]

# Vivado 2026.1 emits ISEWrap.js files that query WMI before starting each
# run.  WMI is unavailable in the managed build environment, while the
# legacy WSH 5.1 path performs the same launch without that query.  Generate
# run scripts first, switch them to that path, then start the runs.
proc patch_run_wrappers {root {lock 0}} {
    set pattern [file join $root build board iq_board.runs * ISEWrap.js]
    foreach path [glob -nocomplain -types f $pattern] {
        file attributes $path -readonly 0
        set fh [open $path r]
        set data [read $fh]
        close $fh
        set data [string map [list \
            "var ISEOldVersionWSH = false;" \
            "var ISEOldVersionWSH = true;"] $data]
        set fh [open $path w]
        puts -nonewline $fh $data
        close $fh
        if {$lock} {file attributes $path -readonly 1}
    }
}

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
reset_run impl_1
set_property strategy Performance_NetDelay_high [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.TCL.PRE $root/scripts/phase3_replication_hook.tcl [get_runs impl_1]
patch_run_wrappers $root 0
launch_runs synth_1 -scripts_only
patch_run_wrappers $root 0
reset_run synth_1
patch_run_wrappers $root 1
launch_runs synth_1 -jobs 1
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]]!="100%"} {error "Synthesis failed"}
patch_run_wrappers $root 0
launch_runs impl_1 -to_step write_bitstream -scripts_only
patch_run_wrappers $root 0
reset_run impl_1
patch_run_wrappers $root 1
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]]!="100%"} {error "Implementation failed"}
source $root/scripts/finish_board.tcl
