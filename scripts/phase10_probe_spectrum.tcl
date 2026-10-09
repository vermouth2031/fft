set root [file normalize [file join [file dirname [info script]] ..]]
set_param general.maxThreads 4
file mkdir $root/build/phase10_probe
read_verilog -sv [list $root/rtl/iq_build_config.sv $root/rtl/spectrum_store.sv $root/rtl/math_units.sv $root/rtl/spectrum_measure.sv]
synth_design -top spectrum_measure -part xc7z020clg400-1 -mode out_of_context -flatten_hierarchy rebuilt
create_clock -period 8.000 [get_ports clk]
report_utilization -file $root/build/phase10_probe/utilization.rpt
report_utilization -hierarchical -file $root/build/phase10_probe/hierarchy.rpt
write_checkpoint -force $root/build/phase10_probe/spectrum.dcp
puts "PHASE10_SPECTRUM_SYNTH_PASS"
