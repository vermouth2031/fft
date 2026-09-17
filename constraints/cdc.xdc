# Only cut the first stage of explicitly implemented synchronizers. XPM
# constrains its own FIFO pointers and handshake paths. No blanket clock cut.
set_false_path -to [get_pins -hier -regexp {.*core/err_sync1_reg\[[0-9]+\]/D}]
set_false_path -to [get_pins -hier -regexp {.*core/cfg_sync_reg\[0\]/D}]
set_false_path -to [get_pins -hier -regexp {.*core/snap_sync_reg\[0\]/D}]
set_false_path -to [get_pins -hier -regexp {.*core/core_reset_reg\[0\]/D}]
