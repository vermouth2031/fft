# Reproducible post-placement optimization of the measured FFT enable net.
set iq_enable_nets [get_nets -hier -filter {NAME =~ */axi_wrapper/ce_w2c}]
if {[llength $iq_enable_nets] != 1} {error "Expected exactly one FFT clock-enable net"}
puts "PHASE3_TARGETED_REPLICATION $iq_enable_nets"
phys_opt_design -force_replication_on_nets $iq_enable_nets
