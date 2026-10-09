open_hw_manager
connect_hw_server -url localhost:3121
open_hw_target
set dev [lindex [get_hw_devices xc7z020*] 0]
refresh_hw_device -update_hw_probes false $dev
set mon [lindex [get_hw_sysmons -of_objects $dev] 0]
refresh_hw_sysmon $mon
set saved {}
set props {CONFIG_REG.SEQ CONFIG_REG.AVG SEQUENCER.CHSEL_TEMP SEQUENCER.CHSEL_INT_AVG SEQUENCER.CHSEL_AUX_AVG SEQUENCER.CHSEL_BRAM_AVG SEQUENCER.CHSEL_VCCO_DDR SEQUENCER.CHSEL_VCCPINT SEQUENCER.CHSEL_VPVN SEQUENCER.AVG_VPVN}
foreach p $props {dict set saved $p [get_property $p $mon]}
set_property CONFIG_REG.SEQ 0000 $mon
commit_hw_sysmon $mon
set_property CONFIG_REG.AVG 11 $mon
foreach p {TEMP INT_AVG AUX_AVG BRAM_AVG VCCO_DDR VCCPINT VPVN} {set_property SEQUENCER.CHSEL_$p 1 $mon}
set_property SEQUENCER.AVG_VPVN 1 $mon
set_property CONFIG_REG.SEQ 0010 $mon
commit_hw_sysmon $mon
set output [lindex $argv 0]
set seconds [lindex $argv 1]
if {$seconds eq ""} {set seconds 30}
set f [open $output w]
puts $f "host_ms,vp_vn,temperature,vccint,vccpint,vccbram,vccoddr"
flush $f
puts "IMON_MONITOR_READY"
for {set i 0} {$i < $seconds*5} {incr i} {
 after 200
 refresh_hw_sysmon $mon
 set row [list [clock milliseconds]]
 foreach p {VP_VN TEMPERATURE VCCINT VCCPINT VCCBRAM VCCO_DDR} {lappend row [get_property $p $mon]}
 puts $f [join $row ,]
 flush $f
}
close $f
foreach p $props {set_property $p [dict get $saved $p] $mon}
commit_hw_sysmon $mon
close_hw_target
disconnect_hw_server
close_hw_manager
