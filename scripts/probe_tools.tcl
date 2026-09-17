set root [file normalize [file join [file dirname [info script]] ..]]
file mkdir $root/build
puts "TOOL_VERSION=[version -short]"
puts "TARGET_PARTS=[get_parts -quiet xc7z020clg400-1]"
create_project tool_probe $root/build/tool_probe -part xc7z020clg400-1 -force
create_ip -name xfft -vendor xilinx.com -library ip -module_name fft_probe
foreach p [lsort [list_property [get_ips fft_probe]]] {
    if {[string match CONFIG.* $p]} { puts "$p=[get_property $p [get_ips fft_probe]]" }
}
puts "PS7=[get_ipdefs -all xilinx.com:ip:processing_system7:*]"
puts "BOARD_PARTS=[get_board_parts -quiet *zybo*]"
close_project
