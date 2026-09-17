set root [file normalize [file join [file dirname [info script]] ..]]
create_project iq_analyzer $root/build/vivado -part xc7z020clg400-1 -force
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property ip_repo_paths {} [current_project]
create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name fft8192
set_property -dict [list \
 CONFIG.transform_length {8192} \
 CONFIG.implementation_options {pipelined_streaming_io} \
 CONFIG.data_format {fixed_point} \
 CONFIG.input_width {24} \
 CONFIG.phase_factor_width {18} \
 CONFIG.scaling_options {scaled} \
 CONFIG.rounding_modes {convergent_rounding} \
 CONFIG.output_ordering {bit_reversed_order} \
 CONFIG.throttle_scheme {nonrealtime} \
 CONFIG.aresetn {true} \
 CONFIG.xk_index {true} \
 CONFIG.ovflo {true} \
 CONFIG.target_clock_frequency {125} \
 CONFIG.target_data_throughput {100}] [get_ips fft8192]
generate_target all [get_ips fft8192]
export_ip_user_files -of_objects [get_ips fft8192] -no_script -sync -force -quiet
close_project
