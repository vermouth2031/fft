set root [file normalize [file join [file dirname [info script]] ..]]
set checkpoint [lindex $argv 0]
if {$checkpoint eq "" || ![file exists $checkpoint]} {error "A final routed checkpoint is required"}
open_checkpoint $checkpoint
set cells [get_cells -hier -filter {REF_NAME =~ RAMB* && (NAME =~ */bank0/* || NAME =~ */bank1/*)}]
if {[llength $cells] != 64} {error "Expected 64 replay RAMB36 cells, got [llength $cells]"}
file mkdir $root/reports
set f [open $root/reports/phase13_replay_port_enables.tsv w]
puts $f "cell\tport_enable\tnet\tdriver_cell\tdriver_type"
set dynamic_enables 0
set constant_enables 0
foreach c [lsort $cells] {
    foreach pin [get_pins -of_objects $c -filter {REF_PIN_NAME == ENARDEN || REF_PIN_NAME == ENBWREN}] {
        set nets [get_nets -of_objects $pin]
        set drivers [get_cells -of_objects [get_pins -of_objects $nets -filter {DIRECTION == OUT}]]
        set refs {}
        foreach d $drivers {lappend refs [get_property REF_NAME $d]}
        puts $f "$c\t[get_property REF_PIN_NAME $pin]\t$nets\t$drivers\t$refs"
        if {[llength $refs] != 1 || [lsearch -exact $refs VCC] >= 0 || [lsearch -exact $refs GND] >= 0} {
            incr constant_enables
        } else { incr dynamic_enables }
    }
}
close $f
if {$dynamic_enables != 128 || $constant_enables != 0} {
    error "Expected 128 dynamic native enables, got dynamic=$dynamic_enables invalid=$constant_enables"
}
puts "REPLAY_NATIVE_ENABLE_INSPECTION cells=[llength $cells] dynamic=$dynamic_enables constant=$constant_enables"
close_design
