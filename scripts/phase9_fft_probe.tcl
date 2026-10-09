set root [file normalize [file join [file dirname [info script]] ..]]
set n [lindex $argv 0]
if {$n ni {16384 32768}} {error "Expected FFT length 16384 or 32768"}
set out $root/build/fft_probe_$n
file mkdir $out
create_project fft_probe $out -part xc7z020clg400-1 -force
set_param general.maxThreads 4
create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name fft_probe
set_property -dict [list CONFIG.transform_length $n CONFIG.implementation_options {pipelined_streaming_io} CONFIG.data_format {fixed_point} CONFIG.input_width {24} CONFIG.phase_factor_width {18} CONFIG.scaling_options {scaled} CONFIG.rounding_modes {convergent_rounding} CONFIG.output_ordering {bit_reversed_order} CONFIG.throttle_scheme {nonrealtime} CONFIG.aresetn {true} CONFIG.xk_index {true} CONFIG.ovflo {true} CONFIG.target_clock_frequency {125} CONFIG.target_data_throughput {125}] [get_ips fft_probe]
generate_target all [get_ips fft_probe]
synth_ip [get_ips fft_probe]
open_checkpoint $out/fft_probe.gen/sources_1/ip/fft_probe/fft_probe.dcp
report_utilization -file $out/utilization.rpt
report_timing_summary -file $out/timing.rpt
puts "FFT_PROBE_PASS length=$n"
exit
