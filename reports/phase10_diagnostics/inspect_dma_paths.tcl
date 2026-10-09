file mkdir D:/fft/fft_phase10_resource_opt/build/diagnostics
set_param general.maxThreads 4
open_checkpoint D:/fft/fft_phase10_resource_opt/build/board/iq_board.runs/impl_1/system_wrapper_postroute_physopt.dcp
set ps [get_cells -hier -filter {REF_NAME == PS7}]
report_timing -to [get_pins -of $ps -filter {DIRECTION == IN && NAME =~ *SAXIHP0*}] -max_paths 15 -file D:/fft/fft_phase10_resource_opt/build/diagnostics/phase10_hp_to_ps.rpt
report_timing -from [get_pins -of $ps -filter {DIRECTION == OUT && NAME =~ *SAXIHP0*}] -max_paths 15 -file D:/fft/fft_phase10_resource_opt/build/diagnostics/phase10_hp_from_ps.rpt
report_timing -through [get_cells -hier -filter {NAME =~ *axi_dma_0*}] -max_paths 30 -file D:/fft/fft_phase10_resource_opt/build/diagnostics/phase10_dma_paths.rpt
puts "PS_CELL $ps"
close_design
