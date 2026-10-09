open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z020*] 0]
refresh_hw_device -update_hw_probes false $dev
set monitor [lindex [get_hw_sysmons -of_objects $dev] 0]
refresh_hw_sysmon $monitor
report_property $monitor
close_hw_target
disconnect_hw_server
close_hw_manager
