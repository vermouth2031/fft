if {$argc!=5} {error "Usage: ELF BIT XSA PS7_INIT OUTPUT"}
lassign $argv elf bit xsa ps7 output
connect
targets -set -filter {name =~ "APU" || name =~ "DAP*"}
rst -system -stop
after 1000
targets -set -filter {name =~ "ARM*#0"}
fpga -file $bit
source $ps7
ps7_init
ps7_post_config
loadhw -hw $xsa -mem-ranges [list {0x40000000 0x4003FFFF}]
rst -processor -stop
dow $elf
con
set done 0
for {set n 0} {$n<80} {incr n} {
 after 250
 set status [lindex [mrd -value 0x0ff00004 1] 0]
 if {$status==2||($status&0x80000000)!=0} {set done 1;break}
}
stop
mrd -size b -bin -file $output 0x0ff00000 328
if {!$done||$status!=2} {error "Independent clock probe failed; inspect mailbox"}
puts "CLOCK_PROBE_PASS"
disconnect
