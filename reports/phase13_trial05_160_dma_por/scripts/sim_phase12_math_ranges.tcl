set root [file normalize [file join [file dirname [info script]] ..]]
create_project phase12_math_ranges $root/build/phase12_math_ranges -part xc7z020clg400-1 -force
add_files -norecurse $root/rtl/math_units.sv
add_files -fileset sim_1 -norecurse [list $root/tests/tb_phase12_math_ranges.sv $root/data/phase12_math_ranges.mem]
set_property top tb_phase12_math_ranges [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
launch_simulation
close_sim
set f [open $root/build/phase12_math_ranges/phase12_math_ranges.sim/sim_1/behav/xsim/simulate.log r]
set text [read $f];close $f
if {[string first "PHASE12_MATH_RANGES_PASS vectors=10220" $text]<0||[string first "Fatal:" $text]>=0} {error "Phase 12 exact math boundary test failed"}
close_project
