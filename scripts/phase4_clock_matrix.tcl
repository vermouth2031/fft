# Probe actual PS7 generated clock divisors in an isolated in-memory design.
# This never programs a board, changes a saved board project, or claims STA.
set root [file normalize [file join [file dirname [info script]] ..]]
if {$argc!=1} {error "Usage: new_output_directory"}
set output [file normalize [lindex $argv 0]]
if {[file exists $output]} {error "Refusing existing experiment directory"}
file mkdir $output
cd $output
set_param board.repoPaths [list $root/vendor/boards]
create_project -in_memory -part xc7z020clg400-1
set_property board_part digilentinc.com:zybo-z7-20:part0:1.2 [current_project]
create_bd_design clock_probe
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1"} [get_bd_cells ps7]
set_property CONFIG.PCW_USE_M_AXI_GP0 {0} [get_bd_cells ps7]
set f [open $output/clock_matrix.csv w]
puts $f "requested_sample_mhz,requested_fft_mhz,actual_sample_mhz,actual_fft_mhz,sample_pin_hz,fft_pin_hz"
foreach pair {{100 125} {102 125} {103 125} {104 125} {125 125} {125 150} {125 156.25}} {
  lassign $pair sample fft
  set_property -dict [list CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_EN_CLK1_PORT {1} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $sample CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ $fft] [get_bd_cells ps7]
  validate_bd_design
  set actual_sample [get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells ps7]]
  set actual_fft [get_property CONFIG.PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ [get_bd_cells ps7]]
  set sample_pin [get_property CONFIG.FREQ_HZ [get_bd_pins ps7/FCLK_CLK0]]
  set fft_pin [get_property CONFIG.FREQ_HZ [get_bd_pins ps7/FCLK_CLK1]]
  puts $f "$sample,$fft,$actual_sample,$actual_fft,$sample_pin,$fft_pin"
  report_property [get_bd_cells ps7] -file $output/ps7_${sample}_${fft}.txt
}
close $f
set f [open $output/SCOPE.txt w]
puts $f "PS7 legal generated-frequency query only. Not implemented/routed and not board-tested. Requested frequencies can round to a different achievable value. Actual waveform rate metadata must follow validated generated clocks."
close $f
puts "PHASE4_CLOCK_MATRIX_COMPLETE"
close_project
