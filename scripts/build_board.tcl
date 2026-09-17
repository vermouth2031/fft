set root [file normalize [file join [file dirname [info script]] ..]]
set_param general.maxThreads 4
set_param board.repoPaths [list $root/vendor/boards]
create_project iq_board $root/build/board -part xc7z020clg400-1 -force
set_property board_part digilentinc.com:zybo-z7-20:part0:1.2 [current_project]
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
add_files -norecurse [glob $root/rtl/*.sv]
add_files -norecurse $root/data/hann_u18_f17.mem
add_files -fileset constrs_1 -norecurse $root/constraints/cdc.xdc
set_property used_in_synthesis false [get_files cdc.xdc]
read_ip $root/build/vivado/iq_analyzer.srcs/sources_1/ip/fft8192/fft8192.xci
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1"} [get_bd_cells ps7]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_EN_CLK1_PORT {1} \
 CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ {125}] [get_bd_cells ps7]
create_bd_cell -type module -reference iq_peripheral iq_0
connect_bd_net [get_bd_pins ps7/FCLK_CLK1] [get_bd_pins iq_0/fft_clk]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master "/ps7/M_AXI_GP0" Clk_master "/ps7/FCLK_CLK0 (100 MHz)" Clk_slave "/ps7/FCLK_CLK0 (100 MHz)" Clk_xbar "/ps7/FCLK_CLK0 (100 MHz)" intc_ip "New AXI Interconnect" master_apm "0"} [get_bd_intf_pins iq_0/S_AXI]
assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *iq_0*}]
if {[llength $seg]!=1} {error "Expected one analyzer address segment; got $seg"}
set_property offset 0x40000000 $seg
set_property range 256K $seg
validate_bd_design
save_bd_design
generate_target all [get_files $root/build/board/iq_board.srcs/sources_1/bd/system/system.bd]
make_wrapper -files [get_files $root/build/board/iq_board.srcs/sources_1/bd/system/system.bd] -top
add_files -norecurse $root/build/board/iq_board.gen/sources_1/bd/system/hdl/system_wrapper.v
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]]!="100%"} {error "Synthesis failed"}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]]!="100%"} {error "Implementation failed"}
source $root/scripts/finish_board.tcl
