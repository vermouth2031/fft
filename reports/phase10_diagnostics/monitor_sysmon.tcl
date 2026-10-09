open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z020*] 0]
refresh_hw_device -update_hw_probes false $dev
set monitor [lindex [get_hw_sysmons -of_objects $dev] 0]
set out [open D:/fft/fft_phase10_resource_opt/build/logs/phase10_sysmon_samples.csv w]
puts $out "time_ms,temperature,vccint,vccpint,vccbram,vccaux,vcco_ddr"
for {set i 0} {$i<150} {incr i} {
    refresh_hw_sysmon $monitor
    set row [list [clock milliseconds]]
    foreach property {TEMPERATURE VCCINT VCCPINT VCCBRAM VCCAUX VCCO_DDR} {
        lappend row [get_property $property $monitor]
    }
    puts $out [join $row ,]
    flush $out
    after 200
}
close $out
close_hw_target
disconnect_hw_server
close_hw_manager
