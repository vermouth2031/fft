# Diagnostic finite capture without Ethernet firmware. Processor stays stopped.
# Usage: xsdb scripts/jtag_capture.tcl <IQ.bin> <output_directory>
set root [file normalize [file join [file dirname [info script]] ..]]
if {$argc!=2} {error "Usage: xsdb jtag_capture.tcl IQ.bin output_directory"}
set input [file normalize [lindex $argv 0]]
set out [file normalize [lindex $argv 1]]
set bytes [file size $input]
if {$bytes ni {32768 65536 98304 131072}} {error "IQ.bin needs 8192/16384/24576/32768 IQ pairs"}
file mkdir $out
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
rst -system
after 3000
targets -set -filter {name =~ "ARM*#0"}
stop
fpga -file $root/artifacts/iq_analyzer.bit
source $root/artifacts/ps7_init.tcl
ps7_init
ps7_post_config
loadhw -hw $root/artifacts/iq_analyzer.xsa -mem-ranges [list {0x40000000 0x4003FFFF}]
if {[mrd -value 0x40000000]!=0x49514131} {error "Analyzer magic mismatch"}
mwr -bin -file $input 0x40010000 [expr {$bytes/4}]
mrd -bin -file $out/replay_readback.bin 0x40010000 [expr {$bytes/4}]
set f [open $input rb];set expected [read $f];close $f
set f [open $out/replay_readback.bin rb];set actual [read $f];close $f
if {$actual ne $expected} {error "Replay RAM read-back mismatch"}
mwr 0x4000001c [expr {$bytes/4}]
mwr 0x40000028 1
mwr 0x40000070 1
mwr 0x4000000c 1
set stopped 0
for {set i 0} {$i<100} {incr i} {
 after 10
 if {([mrd -value 0x40000008]&7)==0} {set stopped 1;break}
}
if {!$stopped} {error "Capture timeout"}
set nf [mrd -value 0x40000050]
set nb [mrd -value 0x40000058]
set errors [mrd -value 0x40000060]
if {$nf>256||$nb>128} {error "Invalid hardware queue counters"}
mwr 0x40000100 1
set samples [mrd -value 0x40000118]
set latency [mrd -value 0x40000124]
set publish_latency [mrd -value 0x40000128]
mrd -bin -file $out/frequency.bin 0x40030000 [expr {$nf*32}]
if {$nb>0} {mrd -bin -file $out/burst.bin 0x40038000 [expr {$nb*16}]} else {close [open $out/burst.bin wb]}
set log [open $out/jtag_capture.txt w]
puts $log "source=JTAG board capture\ninput=$input\nfrequency_records=$nf\nburst_records=$nb\nerrors=$errors\ninput_samples=$samples\nmax_analysis_cycles=$latency\nmax_publish_cycles=$publish_latency\nreplay_readback_verified=true"
close $log
if {$errors!=0||$nf!=($bytes/32768)||$samples!=($bytes/4)||$publish_latency>200000} {error "Capture incomplete; inspect jtag_capture.txt"}
puts "CAPTURE_PASS files in $out. Decode with host/iq_client.py decode."
