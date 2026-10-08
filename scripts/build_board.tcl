set root [file normalize [file join [file dirname [info script]] ..]]
source $root/build/config/generated_clocks.tcl
set sample_rate_hz [expr {round($sample_rate_mhz * 1000000.0)}]
set fft_clock_hz [expr {round($fft_clock_mhz * 1000000.0)}]
set_param general.maxThreads 4
set_param board.repoPaths [list $root/vendor/boards]
create_project iq_board $root/build/board -part xc7z020clg400-1 -force
set_property board_part digilentinc.com:zybo-z7-20:part0:1.2 [current_project]
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
add_files -norecurse [concat [glob $root/rtl/*.sv] [glob $root/rtl/*.svh]]
add_files -norecurse $root/data/hann_quarter_u18_f17.mem
add_files -fileset constrs_1 -norecurse $root/constraints/cdc.xdc
set_property used_in_synthesis false [get_files cdc.xdc]
read_ip $root/build/vivado16k/iq_analyzer.srcs/sources_1/ip/fft8192/fft8192.xci
create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1"} [get_bd_cells ps7]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_EN_CLK1_PORT {1} \
 CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $sample_rate_mhz CONFIG.PCW_FPGA1_PERIPHERAL_FREQMHZ $fft_clock_mhz] [get_bd_cells ps7]
create_bd_cell -type module -reference iq_peripheral iq_0
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0
set_property -dict [list CONFIG.c_include_sg {0} CONFIG.c_include_mm2s {1} CONFIG.c_include_s2mm {0} \
 CONFIG.c_m_axis_mm2s_tdata_width {32} CONFIG.c_mm2s_burst_size {16} CONFIG.c_sg_length_width {23}] [get_bd_cells axi_dma_0]
connect_bd_net [get_bd_pins ps7/FCLK_CLK1] [get_bd_pins iq_0/fft_clk]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] [get_bd_intf_pins iq_0/S_AXIS_IQ]
set axi_clock "/ps7/FCLK_CLK0 ($sample_rate_mhz MHz)"
set axi_config [list Master "/ps7/M_AXI_GP0" Clk_master $axi_clock Clk_slave $axi_clock Clk_xbar $axi_clock intc_ip "New AXI Interconnect" master_apm "0"]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config $axi_config [get_bd_intf_pins iq_0/S_AXI]
set dma_control_config [list Master "/ps7/M_AXI_GP0" Clk_master $axi_clock Clk_slave $axi_clock Clk_xbar $axi_clock intc_ip "Auto" master_apm "0"]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config $dma_control_config [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
set dma_memory_config [list Master "/axi_dma_0/M_AXI_MM2S" Clk_master $axi_clock Clk_slave $axi_clock Clk_xbar $axi_clock intc_ip "New AXI Interconnect" master_apm "0"]
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config $dma_memory_config [get_bd_intf_pins ps7/S_AXI_HP0]
assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *iq_0*}]
if {[llength $seg]!=1} {error "Expected one analyzer address segment; got $seg"}
set_property offset 0x40000000 $seg
set_property range 256K $seg
set dma_seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ *axi_dma_0*Reg*}]
if {[llength $dma_seg]!=1} {error "Expected one AXI DMA control segment; got $dma_seg"}
set_property offset 0x40400000 $dma_seg
set_property range 64K $dma_seg
validate_bd_design
if {[get_property OFFSET $dma_seg] != 0x40400000} {error "AXI DMA control address mismatch"}
if {[get_property CONFIG.c_include_sg [get_bd_cells axi_dma_0]] != 0 ||
    [get_property CONFIG.c_include_mm2s [get_bd_cells axi_dma_0]] != 1 ||
    [get_property CONFIG.c_include_s2mm [get_bd_cells axi_dma_0]] != 0} {
  error "AXI DMA must be simple-mode MM2S only"
}
if {[get_property CONFIG.PCW_USE_S_AXI_HP0 [get_bd_cells ps7]] != 1} {error "PS HP0 is not enabled"}
if {[llength [get_bd_intf_nets -of_objects [get_bd_intf_pins axi_dma_0/M_AXI_MM2S]]]!=1} {
  error "AXI DMA MM2S memory interface is not connected"
}
if {[llength [get_bd_intf_nets -of_objects [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S]]]!=1} {
  error "AXI DMA stream output is not connected"
}
set actual_sample_hz [get_property CONFIG.FREQ_HZ [get_bd_pins ps7/FCLK_CLK0]]
set actual_fft_hz [get_property CONFIG.FREQ_HZ [get_bd_pins ps7/FCLK_CLK1]]
if {$actual_sample_hz != $sample_rate_hz} {error "FCLK_CLK0 mismatch: requested $sample_rate_hz, got $actual_sample_hz"}
if {$actual_fft_hz != $fft_clock_hz} {error "FCLK_CLK1 mismatch: requested $fft_clock_hz, got $actual_fft_hz"}
puts "PHASE8_DDR_DMA_CONFIGURATION_PASS sample_hz=$actual_sample_hz fft_hz=$actual_fft_hz"
save_bd_design
generate_target all [get_files $root/build/board/iq_board.srcs/sources_1/bd/system/system.bd]
make_wrapper -files [get_files $root/build/board/iq_board.srcs/sources_1/bd/system/system.bd] -top
add_files -norecurse $root/build/board/iq_board.gen/sources_1/bd/system/hdl/system_wrapper.v
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
set_property strategy Performance_NetDelay_high [get_runs impl_1]
# Registered PSD addresses remove the former bank-select/LUTRAM critical path.
set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE Default [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE AggressiveExplore [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.TCL.PRE $root/scripts/phase3_replication_hook.tcl [get_runs impl_1]
proc patch_run_wrappers {root {lock 0}} {
    set pattern [file join $root build board iq_board.runs * ISEWrap.js]
    foreach path [glob -nocomplain -types f $pattern] {
        file attributes $path -readonly 0
        set fh [open $path r]
        set data [read $fh]
        close $fh
        set data [string map [list \
            "var ISEOldVersionWSH = false;" \
            "var ISEOldVersionWSH = true;"] $data]
        set fh [open $path w]
        puts -nonewline $fh $data
        close $fh
        if {$lock} {file attributes $path -readonly 1}
    }
}

launch_runs synth_1 -scripts_only
patch_run_wrappers $root 0
reset_run synth_1
patch_run_wrappers $root 1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]]!="100%"} {error "Synthesis failed"}
patch_run_wrappers $root 0
launch_runs impl_1 -to_step write_bitstream -scripts_only
patch_run_wrappers $root 0
reset_run impl_1
patch_run_wrappers $root 1
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]]!="100%"} {error "Implementation failed"}
source $root/scripts/finish_board.tcl
