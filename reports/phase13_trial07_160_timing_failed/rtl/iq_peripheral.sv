`timescale 1ns/1ps
`include "iq_clock_attributes.svh"
// AXI4-Lite control/replay/results. All bus and source logic uses the configured sample clock.
module iq_peripheral(
 (* X_INTERFACE_PARAMETER=`IQ_AXI_CLOCK_PARAMETER *)
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *) input wire s_axi_aclk,
 (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *)
 (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *) input wire s_axi_aresetn,
 (* X_INTERFACE_PARAMETER=`IQ_FFT_CLOCK_PARAMETER *)
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 fft_clk CLK" *) input wire fft_clk,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *) input wire [17:0] s_axi_awaddr,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output reg [1:0] s_axi_bresp,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output reg s_axi_bvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
 (* X_INTERFACE_PARAMETER="PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 18, READ_WRITE_MODE READ_WRITE" *)
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [17:0] s_axi_araddr,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output reg [31:0] s_axi_rdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output reg [1:0] s_axi_rresp,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output reg s_axi_rvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready,
 (* X_INTERFACE_PARAMETER="TDATA_NUM_BYTES 4, HAS_TKEEP 1, HAS_TLAST 1" *)
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS_IQ TDATA" *) input wire [31:0] s_axis_iq_tdata,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS_IQ TKEEP" *) input wire [3:0] s_axis_iq_tkeep,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS_IQ TVALID" *) input wire s_axis_iq_tvalid,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS_IQ TREADY" *) output wire s_axis_iq_tready,
 (* X_INTERFACE_INFO="xilinx.com:interface:axis:1.0 S_AXIS_IQ TLAST" *) input wire s_axis_iq_tlast);
 localparam integer N=iq_build_config::FFT_LENGTH,LOGN=iq_build_config::FFT_LOG2;
 localparam integer FREQ_CAP=iq_build_config::FREQUENCY_RECORDS,FREQ_LOG=iq_build_config::FREQUENCY_RECORDS_LOG2;
 wire clk=s_axi_aclk,rst=!s_axi_aresetn;
 reg aw_hold,w_hold;reg [17:0] wa;reg [31:0] wd;reg [3:0] ws;
 // A physical local copy for acknowledgment comparisons keeps the shared
 // write-data bus fanout away from the consumer update path.
 (* DONT_TOUCH="TRUE" *) reg [31:0] acknowledgment_data;
 reg [1:0] read_delay;reg [17:0] ra;
 reg [31:0] read_group[0:3];reg [3:0] read_mapped;
 assign s_axi_awready=!aw_hold&&!s_axi_bvalid;
 assign s_axi_wready=!w_hold&&!s_axi_bvalid;
 wire write_fire=aw_hold&&w_hold&&!s_axi_bvalid&&read_delay==0;
 assign s_axi_arready=read_delay==0&&!s_axi_rvalid;
 reg [63:0] tick;
 localparam STOPPED=0,RESET_CORE=1,WAIT_CORE=2,RUNNING=3,DRAINING=4;
 reg [2:0] run_state;reg [15:0] wait_count;reg stop_pending,abort_pending;
 wire active=run_state!=STOPPED;
 wire acquisition_reset=rst||run_state==RESET_CORE;
 reg [31:0] replay_length,replay_start,replay_mode,window_mode,roi_l,roi_h;
 reg [35:0] ton,toff;reg [15:0] kon,koff;reg [31:0] max_burst;
 // Legal acquisitions limit max_burst to 1..1048576. Keep the full host
 // register/validation, but distribute a local 21-bit copy to the core.
 // Configuration settles during the existing core reset before any sample.
 reg [20:0] core_max_burst;
 always @(posedge clk)if(rst)core_max_burst<=21'd1048576;else core_max_burst<=max_burst[20:0];
 reg [31:0] detector_mode,gap_min;
 // Capture one-hot configuration decode with AW; each register then uses
 // a short write enable independent of the control-register response tree.
 reg [14:0] config_address;
 reg control_address,frequency_ack_address,burst_ack_address;
 reg [5:0] metadata_address;
 always @(posedge clk)begin
   if(rst)begin
     config_address<=0;control_address<=0;frequency_ack_address<=0;burst_ack_address<=0;metadata_address<=0;
   end
   else if(s_axi_awvalid&&s_axi_awready)begin
     control_address<=s_axi_awaddr==18'h00c;
     frequency_ack_address<=s_axi_awaddr==18'h054;
     burst_ack_address<=s_axi_awaddr==18'h05c;
     metadata_address<={s_axi_awaddr==18'h1a0,s_axi_awaddr==18'h19c,s_axi_awaddr==18'h198,
       s_axi_awaddr==18'h194,s_axi_awaddr==18'h190,s_axi_awaddr==18'h18c};
     config_address[0]<=s_axi_awaddr==18'h01c;
     config_address[1]<=s_axi_awaddr==18'h020;
     config_address[2]<=s_axi_awaddr==18'h024;
     config_address[3]<=s_axi_awaddr==18'h028;
     config_address[4]<=s_axi_awaddr==18'h02c;
     config_address[5]<=s_axi_awaddr==18'h030;
     config_address[6]<=s_axi_awaddr==18'h034;
     config_address[7]<=s_axi_awaddr==18'h038;
     config_address[8]<=s_axi_awaddr==18'h03c;
     config_address[9]<=s_axi_awaddr==18'h040;
     config_address[10]<=s_axi_awaddr==18'h044;
     config_address[11]<=s_axi_awaddr==18'h048;
     config_address[12]<=s_axi_awaddr==18'h04c;
     config_address[13]<=s_axi_awaddr==18'h084;
     config_address[14]<=s_axi_awaddr==18'h088;
   end
 end
 always @(posedge clk)begin
   if(rst)begin
     replay_length<=32768;replay_start<=0;replay_mode<=0;window_mode<=1;
     roi_l<=0;roi_h<=N-1;ton<=1048576;toff<=262144;kon<=8;koff<=32;max_burst<=1048576;
     detector_mode<=0;gap_min<=32;
   end else if(write_fire&&ws!=0&&!active)begin
     if(config_address[0])begin replay_length<=merge_bytes(replay_length,wd,ws); end
     if(config_address[1])begin replay_start<=merge_bytes(replay_start,wd,ws); end
     if(config_address[2])begin replay_mode<=merge_bytes(replay_mode,wd,ws); end
     if(config_address[3])begin window_mode<=merge_bytes(window_mode,wd,ws); end
     if(config_address[4])begin roi_l<=merge_bytes(roi_l,wd,ws); end
     if(config_address[5])begin roi_h<=merge_bytes(roi_h,wd,ws); end
     if(config_address[6])begin ton[31:0]<=merge_bytes(ton[31:0],wd,ws); end
     if(config_address[7])begin if(ws[0])ton[35:32]<=wd[3:0]; end
     if(config_address[8])begin toff[31:0]<=merge_bytes(toff[31:0],wd,ws); end
     if(config_address[9])begin if(ws[0])toff[35:32]<=wd[3:0]; end
     if(config_address[10])begin kon<=merge_bytes({16'd0,kon},wd,ws); end
     if(config_address[11])begin koff<=merge_bytes({16'd0,koff},wd,ws); end
     if(config_address[12])begin max_burst<=merge_bytes(max_burst,wd,ws); end
     if(config_address[13])begin detector_mode<=merge_bytes(detector_mode,wd,ws); end
     if(config_address[14])begin gap_min<=merge_bytes(gap_min,wd,ws); end
   end
 end

 reg [31:0] epoch,config_id,config_dirty;
 reg [31:0] freq_consumer,burst_consumer,host_errors;
 wire [31:0] freq_producer,burst_producer,freq_dropped,burst_dropped;
 wire freq_busy,burst_busy,freq_has_space;
 wire [31:0] freq_read,burst_read;
 wire [7:0] core_errors;
 wire [31:0] error_status=host_errors|{24'd0,core_errors}|(freq_dropped!=0?32'h10000:0)|(burst_dropped!=0?32'h20000:0);
 wire config_ok=replay_length>=N&&replay_length<=32768&&replay_length[LOGN-1:0]==0&&
   replay_start<32768&&replay_start+replay_length<=32768&&replay_mode<=1&&window_mode<=1&&
   roi_l<=roi_h&&roi_h<N&&ton>toff&&kon!=0&&koff!=0&&
   detector_mode<=1&&gap_min>=1&&gap_min<=65535&&
   max_burst>=(detector_mode==1?32'd1:{16'd0,kon})&&max_burst<=1048576;
 reg config_valid,cfg_replay,cfg_threshold,cfg_detector,cfg_burst;
 reg [31:0] replay_last;
 always @(posedge clk)begin
   replay_last<=replay_length-32'd1;
   if(rst)begin cfg_replay<=0;cfg_threshold<=0;cfg_detector<=0;cfg_burst<=0;end
   else begin
     cfg_replay<=replay_length>=N&&replay_length<=32768&&replay_length[LOGN-1:0]==0&&replay_start<32768&&replay_start+replay_length<=32768&&replay_mode<=1&&window_mode<=1;
     cfg_threshold<=roi_l<=roi_h&&roi_h<N&&ton>toff&&kon!=0&&koff!=0;
     cfg_detector<=detector_mode<=1&&gap_min>=1&&gap_min<=65535;
     cfg_burst<=max_burst<=1048576&&((detector_mode==1&&max_burst>=1)||(detector_mode!=1&&max_burst>={16'd0,kon}));
   end
 end
 reg drain_counts_match;
 // During DRAINING, issued is fixed and completed/accounted only advance
 // toward it. Delay the stable equality by one clock to separate the sum
 // from FSM/error-control fanout. Busy/valid are still checked live.
 always @(posedge clk)begin
   if(acquisition_reset)drain_counts_match<=0;
   else drain_counts_match<=completed==(issued>>LOGN)&&freq_producer+freq_dropped==completed;
 end
 always @(posedge clk)if(rst)config_valid<=0;else config_valid<=cfg_replay&&cfg_threshold&&cfg_detector&&cfg_burst;
 reg [63:0] issued;
 reg [14:0] replay_ptr;reg [31:0] replay_pos;
 reg host_bank,active_bank,pending_bank,pending_valid;
 wire [1:0] bank_ready;
 wire [31:0] bank_length0,bank_length1,bank_block0,bank_block1,bank_crc0,bank_crc1;
 reg [31:0] current_block_id,switch_count,stream_write_rejected,stream_errors;
 reg [63:0] last_switch_tick;
 reg loader_target,loader_active,loader_done;
 reg loader_write_allowed,loader_expected_last;
 reg [3:0] loader_word_error_bits;
 reg [31:0] loader_expected,loader_block,loader_expected_crc,loader_received;
 reg [31:0] loader_crc_state,loader_computed_crc,loader_transfers,loader_errors;
 reg [31:0] loader_word;reg [3:0] loader_word_keep;reg loader_word_last;reg [2:0] loader_crc_byte;
 wire [31:0] host_bank_length=host_bank?bank_length1:bank_length0;
 // Register metadata checks before READY/SWITCH command fanout. Metadata
 // writes settle before the next AXI command can execute.
 reg bank0_metadata_valid,bank1_metadata_valid;
 always @(posedge clk)begin
   if(rst)begin bank0_metadata_valid<=0;bank1_metadata_valid<=0;end
   else begin
     bank0_metadata_valid<=bank_length0>=N&&bank_length0<=32768&&bank_length0[LOGN-1:0]==0&&bank_length0==replay_length;
     bank1_metadata_valid<=bank_length1>=N&&bank_length1<=32768&&bank_length1[LOGN-1:0]==0&&bank_length1==replay_length;
   end
 end
 wire host_bank_metadata_valid=host_bank?bank1_metadata_valid:bank0_metadata_valid;
 // Exact circular interval, including full 32-bit counter wrap. Parallel
 // comparisons replace two subtractions followed by another comparison.
 // Parallel byte comparisons shorten the carry chain without changing the
 // unsigned 32-bit ordering, including values around the counter wrap.
 function automatic ge32(input [31:0] a,b);
   ge32=(a[31:24]>b[31:24])||
     ((a[31:24]==b[31:24])&&(a[23:16]>b[23:16]))||
     ((a[31:16]==b[31:16])&&(a[15:8]>b[15:8]))||
     ((a[31:8]==b[31:8])&&(a[7:0]>=b[7:0]));
 endfunction
 function automatic in_modular_interval(input [31:0] value,first,last);
   in_modular_interval=ge32(last,first)?(ge32(value,first)&&ge32(last,value)):
     (ge32(value,first)||ge32(last,value));
 endfunction
 function automatic [31:0] crc32_byte(input [31:0] crc,input [7:0] data);
   reg [31:0] c;integer bit_index;
   begin
     c=crc^data;
     for(bit_index=0;bit_index<8;bit_index=bit_index+1)c=(c>>1)^(32'hedb88320&{32{c[0]}});
     crc32_byte=c;
   end
 endfunction
 wire dma_fire=s_axis_iq_tvalid&&s_axis_iq_tready;
 wire [31:0] dma_crc_next=crc32_byte(loader_crc_state,loader_word[7:0]);
 wire [31:0] loader_word_errors=(loader_word_keep!=4'hf ? 32'h2 : 0)|
   (loader_received>=loader_expected ? 32'h4 : 0)|
   (loader_received+1==loader_expected&&!loader_word_last ? 32'h8 : 0);
 // CRC processing leaves four clocks between accepted AXIS words. Prepare
 // the NEXT word's range check before received advances, keeping the wide
 // comparison out of the BRAM write-enable fanout path. Error accounting
 // still uses the full 32-bit counters, including malformed overlong blocks.
 wire dma_loader_write=dma_fire&&loader_write_allowed&&s_axis_iq_tkeep==4'hf;
 assign s_axis_iq_tready=loader_active&&loader_crc_byte==0&&!commit_busy&&!loader_abort;
 wire [31:0] replay_q,host_replay_q;
 wire [31:0] replay_q0,replay_q1,host_replay_q0,host_replay_q1;
 reg [31:0] core_iq;
 reg source_valid,source_finish,core_valid,core_finish;
 reg [63:0] core_tick;
 wire issue=run_state==RUNNING;
 wire final_issue=issue&&((replay_mode==0&&replay_pos==replay_last)||
   (stop_pending&&issued[LOGN-1:0]==N-1));
 wire bank0_writable=(!active||active_bank!=0)&&(!pending_valid||pending_bank!=0)&&(!loader_active||loader_target!=0);
 wire bank1_writable=(!active||active_bank!=1)&&(!pending_valid||pending_bank!=1)&&(!loader_active||loader_target!=1);
 wire replay_write=write_fire&&wa>=18'h10000&&wa<18'h30000&&wa[1:0]==0&&
   (host_bank?bank1_writable:bank0_writable);
 wire [14:0] host_ram_addr=replay_write?((wa-18'h10000)>>2):((ra-18'h10000)>>2);
 wire [14:0] bank_host_addr=dma_loader_write?loader_received[14:0]:host_ram_addr;
 wire [31:0] bank_host_wdata=dma_loader_write?s_axis_iq_tdata:wd;
 wire [3:0] bank_host_wstrb=dma_loader_write?4'hf:ws;
 // Address, strobes and data advance with the registered write enables.
 // Port B remains a synchronous one-cycle read; AXI reads consume A below.
 reg [14:0] bank_host_addr_q;
 reg [31:0] bank_host_wdata_q;
 reg [3:0] bank_host_wstrb_q;
 reg bank0_host_we,bank1_host_we;
 always @(posedge clk)begin
   bank_host_addr_q<=bank_host_addr;bank_host_wdata_q<=bank_host_wdata;bank_host_wstrb_q<=bank_host_wstrb;
   if(rst)begin bank0_host_we<=0;bank1_host_we<=0;end
   else begin
     bank0_host_we<=(replay_write&&!host_bank)||(dma_loader_write&&!loader_target);
     bank1_host_we<=(replay_write&&host_bank)||(dma_loader_write&&loader_target);
   end
 end
 // RAM data returns one cycle after the address/bank decision. Carry the
 // bank selection alongside that read, including the last sample before a
 // switch. Only the bank supplying that sample needs its replay port enabled.
 reg replay_bank_q;
 always @(posedge clk)begin
   if(rst)replay_bank_q<=0;
   else if(issue)replay_bank_q<=active_bank;
 end
 wire bank0_replay_en=issue&&!active_bank;
 wire bank1_replay_en=issue&&active_bank;
 // The registered host address is valid at read_delay==2; the response at
 // read_delay==3 sees this synchronous read. Writes use the same port enable.
 wire host_ram_read=read_delay==2&&ra>=18'h10000&&ra<18'h30000&&ra[1:0]==0;
 wire bank0_host_en=bank0_host_we||(host_ram_read&&!host_bank);
 wire bank1_host_en=bank1_host_we||(host_ram_read&&host_bank);
 assign replay_q=replay_bank_q?replay_q1:replay_q0;
 assign host_replay_q=host_bank?host_replay_q1:host_replay_q0;
 iq_replay_bank bank0(.clk(clk),.host_addr(bank_host_addr_q),
   .host_en(bank0_host_en),.host_we(bank0_host_we),.replay_en(bank0_replay_en),
   .host_wstrb(bank_host_wstrb_q),.host_wdata(bank_host_wdata_q),.host_q(host_replay_q0),.replay_addr(replay_ptr),.replay_q(replay_q0));
 iq_replay_bank bank1(.clk(clk),.host_addr(bank_host_addr_q),
   .host_en(bank1_host_en),.host_we(bank1_host_we),.replay_en(bank1_replay_en),
   .host_wstrb(bank_host_wstrb_q),.host_wdata(bank_host_wdata_q),.host_q(host_replay_q1),.replay_addr(replay_ptr),.replay_q(replay_q1));
 reg diagnostic_toggle,diagnostic_busy,diagnostic_valid;
 reg [31:0] diagnostic_sequence;
 wire diagnostic_arrived;wire [223:0] fft_diagnostic;
 wire [63:0] accepted_samples;wire [31:0] input_rejected;wire [12:0] input_high_water;
 reg [63:0] issued_snapshot,accepted_snapshot,diagnostic_arrival_tick;
 reg [31:0] rejected_snapshot;reg [12:0] high_water_snapshot;
 reg [223:0] fft_diagnostic_snapshot;
 wire core_ready,freq_valid,burst_valid;wire [1023:0] freq_record;wire [511:0] burst_record;
 wire [63:0] samples;wire [31:0] completed,max_latency;
 reg [31:0] publish_latency_max;
 reg [63:0] publish_start;
 reg freq_busy_previous;
 reg snap_request,snapshot_valid,snapshot_pending;
 wire snap_we,snap_done;wire [9:0] snap_addr;wire [63:0] snap_data;wire [31:0] snap_window;
 (* ram_style="block" *) reg [63:0] snapshot_mem[0:1023];
 reg [63:0] snapshot_q;
 reg snap_send;wire snap_received,snap_arrived,fft_reset;
 wire [31:0] snapshot_window_cdc;
 reg [31:0] snapshot_window;
 always @(posedge fft_clk)begin
   if(fft_reset)snap_send<=0;
   else if(snap_done)snap_send<=1;
   else if(snap_received)snap_send<=0;
 end
 xpm_cdc_handshake #(.WIDTH(32),.DEST_EXT_HSK(0),.DEST_SYNC_FF(3),.SRC_SYNC_FF(3),.INIT_SYNC_FF(1)) snapshot_cdc(
 .src_clk(fft_clk),.src_in(snap_window),.src_send(snap_send),.src_rcv(snap_received),
 .dest_clk(clk),.dest_out(snapshot_window_cdc),.dest_req(snap_arrived),.dest_ack(1'b0));
 always @(posedge fft_clk)if(snap_we)snapshot_mem[snap_addr]<=snap_data;
 always @(posedge clk)snapshot_q<=snapshot_mem[ra[12:3]];
 analyzer_core core(.src_clk(clk),.fft_clk(fft_clk),.rst(acquisition_reset),
   .diagnostic_toggle(diagnostic_toggle),.diagnostic_arrived(diagnostic_arrived),.fft_diagnostic(fft_diagnostic),
   .accepted_samples(accepted_samples),.input_rejected(input_rejected),.input_high_water(input_high_water),
   .valid(core_valid),.iq(core_iq),.finish(core_finish),.tick(core_tick),.hann(window_mode[0]),
   .roi_low(roi_l[LOGN-1:0]),.roi_high(roi_h[LOGN-1:0]),.ton(ton),.toff(toff),.kon(kon),.koff(koff),.max_burst({11'd0,core_max_burst}),
   .detector_mode(detector_mode[0]),.gap_min(gap_min[15:0]),
   .epoch(epoch),.config_id(config_id),.ready(core_ready),.fft_reset(fft_reset),.freq_valid(freq_valid),.freq_record(freq_record),
   .burst_valid(burst_valid),.burst_record(burst_record),.samples(samples),.completed(completed),.max_latency(max_latency),
   .errors(core_errors),.snap_request(snap_request),.snap_we(snap_we),.snap_addr(snap_addr),.snap_data(snap_data),.snap_done(snap_done),.snap_window(snap_window));
 record_ring #(.WORDS_LOG2(5),.RECORDS_LOG2(FREQ_LOG)) freq_ring(.clk(clk),.rst(acquisition_reset),.push(freq_valid),.record_data(freq_record),
   .consumer(freq_consumer),.producer(freq_producer),.dropped(freq_dropped),.busy(freq_busy),.has_space(freq_has_space),.read_addr(ra[FREQ_LOG+6:2]),.read_data(freq_read));
 record_ring #(.WORDS_LOG2(4),.RECORDS_LOG2(7)) burst_ring(.clk(clk),.rst(acquisition_reset),.push(burst_valid),.record_data(burst_record),
   .consumer(burst_consumer),.producer(burst_producer),.dropped(burst_dropped),.busy(burst_busy),.read_addr(ra[12:2]),.read_data(burst_read));
 function automatic [31:0] merge_bytes(input [31:0] old_value,new_value,input [3:0] strb);
   integer b;begin for(b=0;b<4;b=b+1)merge_bytes[b*8+:8]=strb[b]?new_value[b*8+:8]:old_value[b*8+:8];end
 endfunction
 wire [31:0] strobed_data=merge_bytes(0,wd,ws);
 // Phase13: terminal CRC capture, validation and bank publication are separate.
 wire loader_command=write_fire&&wa==18'h1c0&&ws!=0;
 wire loader_abort=loader_command&&strobed_data[1];
 wire loader_start_request=loader_command&&strobed_data[0]&&!loader_abort;
 wire loader_start_allowed=!loader_active&&!(active&&loader_target==active_bank)&&
   !(pending_valid&&loader_target==pending_bank)&&loader_expected>=N&&
   loader_expected<=32768&&loader_expected[LOGN-1:0]==0;
 wire loader_start=loader_start_request&&loader_start_allowed;
 wire loader_clear=loader_command&&strobed_data[2]&&!loader_active;
 wire loader_bad_target=write_fire&&wa==18'h1c4&&ws!=0&&(loader_active||wd[31:1]!=0);
 wire [31:0] loader_command_errors=(loader_start_request&&!loader_start_allowed?32'h40:0)|
   (loader_bad_target?32'h80:0)|(loader_abort?32'h20:0);
 wire commit_busy,commit_finish,commit_target,commit0_raw,commit1_raw;
 wire [31:0] commit_length,commit_block,commit_crc,commit_errors;
 // During terminal commit loader_active is still asserted: every START or
 // target write is illegal regardless of run_state, ownership or length.
 // Do not route those redundant validation cones into bank publication.
 wire loader_target_request=write_fire&&wa==18'h1c4&&ws!=0;
 wire commit_legal=!loader_abort&&loader_errors==0&&!loader_start_request&&!loader_target_request;
 wire commit0=commit0_raw&&commit_legal,commit1=commit1_raw&&commit_legal;
 iq_dma_commit dma_commit(.clk(clk),.rst(rst),.cancel(loader_abort),
   .start(loader_crc_byte==4&&loader_word_last&&!loader_abort),.target(loader_target),
   .length(loader_expected),.block_id(loader_block),.expected_crc(loader_expected_crc),
   .computed_crc(dma_crc_next^32'hffffffff),
   .errors(loader_errors|{28'd0,loader_word_error_bits}|(!loader_expected_last?32'h1:0)),
   .finish(commit_finish),.commit0(commit0_raw),.commit1(commit1_raw),.target_q(commit_target),
   .length_q(commit_length),.block_q(commit_block),.crc_q(commit_crc),.error_q(commit_errors),.busy(commit_busy));
 // A single error writer preserves faults arriving during terminal validation.
 always @(posedge clk)begin
   if(rst)loader_errors<=0;
   else if(loader_start)loader_errors<=0;
   else loader_errors<=(loader_clear?32'd0:loader_errors)|loader_command_errors|
     (loader_crc_byte==4?{28'd0,loader_word_error_bits}:32'd0)|
     (commit_finish&&!loader_abort?commit_errors:32'd0);
 end
 wire bank_command=write_fire&&wa==18'h184&&ws!=0;
 wire host_bank_writable=host_bank?bank1_writable:bank0_writable;
 wire manual_ready=bank_command&&strobed_data[0]&&host_bank_metadata_valid&&host_bank_writable;
 wire host_bank_clearable=!(active&&host_bank==active_bank)&&!(loader_active&&host_bank==loader_target)&&
   (!(pending_valid&&host_bank==pending_bank)||(bank_command&&strobed_data[2]));
 wire manual_invalidate=bank_command&&strobed_data[3]&&host_bank_clearable;
 wire bank_release=run_state==RUNNING&&pending_valid&&issued[LOGN-1:0]==N-1;
 wire loader_invalidate=loader_start||loader_abort||(commit_finish&&!(commit0||commit1));
 wire host_invalidate=(replay_write&&ws!=0)||manual_invalidate;
 wire metadata_write=write_fire&&ws!=0;
 reg [31:0] metadata_host_data;
 reg [3:0] metadata_host_strobe;
 reg [2:0] metadata0_we,metadata1_we;
 always @(posedge clk)begin
   metadata_host_data<=wd;metadata_host_strobe<=ws;
   if(rst)begin metadata0_we<=0;metadata1_we<=0;end
   else begin
     metadata0_we<={metadata_write&&metadata_address[4]&&bank0_writable,
       metadata_write&&metadata_address[2]&&bank0_writable,metadata_write&&metadata_address[0]&&bank0_writable};
     metadata1_we<={metadata_write&&metadata_address[5]&&bank1_writable,
       metadata_write&&metadata_address[3]&&bank1_writable,metadata_write&&metadata_address[1]&&bank1_writable};
   end
 end
 iq_bank_metadata metadata0(.clk(clk),.rst(rst),.release_bank(bank_release&&!active_bank),
   .invalidate((host_invalidate&&!host_bank)||(loader_invalidate&&!loader_target)),
   .host_ready(manual_ready&&!host_bank),
   .host_length_we(metadata0_we[0]),.host_block_we(metadata0_we[1]),
   .host_crc_we(metadata0_we[2]),.host_data(metadata_host_data),.host_strobe(metadata_host_strobe),
   .commit(commit0),.commit_length(commit_length),.commit_block(commit_block),.commit_crc(commit_crc),
   .ready(bank_ready[0]),.length(bank_length0),.block_id(bank_block0),.crc(bank_crc0));
 iq_bank_metadata metadata1(.clk(clk),.rst(rst),.release_bank(bank_release&&active_bank),
   .invalidate((host_invalidate&&host_bank)||(loader_invalidate&&loader_target)),
   .host_ready(manual_ready&&host_bank),
   .host_length_we(metadata1_we[0]),.host_block_we(metadata1_we[1]),
   .host_crc_we(metadata1_we[2]),.host_data(metadata_host_data),.host_strobe(metadata_host_strobe),
   .commit(commit1),.commit_length(commit_length),.commit_block(commit_block),.commit_crc(commit_crc),
   .ready(bank_ready[1]),.length(bank_length1),.block_id(bank_block1),.crc(bank_crc1));

 reg [63:0] tick_snapshot,samples_snapshot;
 reg [31:0] completed_snapshot,latency_snapshot,publish_snapshot;
 wire [63:0] publish_elapsed=tick-publish_start;
 reg [31:0] publish_elapsed_low;
 reg publish_elapsed_high,publish_update;
 always @(posedge clk)begin
   if(rst)begin
     aw_hold<=0;w_hold<=0;wa<=0;wd<=0;acknowledgment_data<=0;ws<=0;s_axi_bvalid<=0;s_axi_bresp<=0;
     s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;read_delay<=0;ra<=0;read_mapped<=0;
     diagnostic_toggle<=0;diagnostic_busy<=0;diagnostic_valid<=0;diagnostic_sequence<=0;
     issued_snapshot<=0;accepted_snapshot<=0;rejected_snapshot<=0;high_water_snapshot<=0;
     fft_diagnostic_snapshot<=0;diagnostic_arrival_tick<=0;
     tick<=0;run_state<=STOPPED;wait_count<=0;stop_pending<=0;abort_pending<=0;issued<=0;replay_ptr<=0;replay_pos<=0;
     host_bank<=0;active_bank<=0;pending_bank<=0;pending_valid<=0;
     current_block_id<=0;switch_count<=0;stream_write_rejected<=0;stream_errors<=0;last_switch_tick<=0;
     loader_target<=0;loader_active<=0;loader_done<=0;loader_write_allowed<=0;loader_expected_last<=0;loader_word_error_bits<=0;loader_expected<=0;loader_block<=0;loader_expected_crc<=0;
     loader_received<=0;loader_crc_state<=32'hffffffff;loader_computed_crc<=0;loader_transfers<=0;
     loader_word<=0;loader_word_keep<=0;loader_word_last<=0;loader_crc_byte<=0;
     source_valid<=0;source_finish<=0;core_valid<=0;core_finish<=0;core_iq<=0;core_tick<=0;



     epoch<=0;config_id<=1;config_dirty<=0;freq_consumer<=0;burst_consumer<=0;host_errors<=0;
     snap_request<=0;snapshot_valid<=0;snapshot_pending<=0;snapshot_window<=0;
     tick_snapshot<=0;samples_snapshot<=0;completed_snapshot<=0;latency_snapshot<=0;publish_snapshot<=0;
     publish_latency_max<=0;publish_start<=0;freq_busy_previous<=0;publish_update<=0;
   end else begin
     if(dma_fire)begin
       loader_word<=s_axis_iq_tdata;loader_word_keep<=s_axis_iq_tkeep;
       loader_word_last<=s_axis_iq_tlast;loader_crc_byte<=1;
     end
     if(loader_crc_byte!=0)begin
       // Fixed byte position removes the subtract/index mux from CRC logic.
       // Each accepted word still takes the same four CRC processing clocks.
       loader_word<={8'd0,loader_word[31:8]};
       loader_crc_state<=dma_crc_next;
       if(loader_crc_byte==3)begin
         loader_write_allowed<=(loader_received+32'd1)<loader_expected;
         loader_expected_last<=(loader_received+32'd1)==loader_expected;
         loader_word_error_bits<=loader_word_errors[3:0];
       end
       if(loader_crc_byte==4)begin
         loader_crc_byte<=0;loader_received<=loader_received+1;
         if(loader_word_last)loader_computed_crc<=dma_crc_next^32'hffffffff;
       end else loader_crc_byte<=loader_crc_byte+1;
     end
     if(commit_finish&&!loader_abort)begin
       loader_active<=0;loader_done<=commit0||commit1;
       if(commit0||commit1)loader_transfers<=loader_transfers+1;
     end
     if(diagnostic_arrived&&diagnostic_busy)begin
       fft_diagnostic_snapshot<=fft_diagnostic;diagnostic_busy<=0;diagnostic_valid<=1;
       diagnostic_arrival_tick<=tick;diagnostic_sequence<=diagnostic_sequence+1;
     end
     tick<=tick+1;source_valid<=issue;source_finish<=final_issue;
     core_iq<=replay_q;core_valid<=source_valid;core_finish<=source_finish;core_tick<=tick;
     freq_busy_previous<=freq_busy;
     if(freq_valid&&!freq_busy&&freq_has_space)publish_start<=freq_record[8*32+:64];
     publish_update<=freq_busy_previous&&!freq_busy;
     if(freq_busy_previous&&!freq_busy)begin
       publish_elapsed_low<=publish_elapsed[31:0];publish_elapsed_high<=|publish_elapsed[63:32];
     end
     if(publish_update&&(publish_elapsed_high||publish_elapsed_low>publish_latency_max))publish_latency_max<=publish_elapsed_low;
     if(acquisition_reset)begin
       diagnostic_toggle<=0;diagnostic_busy<=0;diagnostic_valid<=0;
       freq_consumer<=0;burst_consumer<=0;publish_latency_max<=0;freq_busy_previous<=0;publish_update<=0;
       snap_request<=0;snapshot_valid<=0;snapshot_pending<=0;
     end else begin
       if(snap_arrived&&snapshot_pending)begin snapshot_valid<=1;snapshot_pending<=0;snap_request<=0;snapshot_window<=snapshot_window_cdc;end
     end
     case(run_state)
       RESET_CORE:if(wait_count==31)begin run_state<=abort_pending?STOPPED:WAIT_CORE;wait_count<=0;end else wait_count<=wait_count+1;
       WAIT_CORE:if(core_ready)begin run_state<=RUNNING;issued<=0;replay_pos<=0;replay_ptr<=replay_start[14:0];end
       RUNNING:begin
         issued<=issued+1;
         if(pending_valid&&issued[LOGN-1:0]==N-1)begin
           active_bank<=pending_bank;pending_valid<=0;replay_pos<=0;replay_ptr<=0;
           current_block_id<=pending_bank?bank_block1:bank_block0;
           switch_count<=switch_count+1;last_switch_tick<=tick;
         end else if(replay_pos==replay_last)begin replay_pos<=0;replay_ptr<=replay_start[14:0];end
         else begin replay_pos<=replay_pos+1;replay_ptr<=replay_ptr+1;end
         if(final_issue)begin run_state<=DRAINING;wait_count<=0;end
         if(core_errors!=0)stop_pending<=1;
       end
       DRAINING:begin
         if(wait_count!=65535)wait_count<=wait_count+1;
         if(wait_count>=1024&&drain_counts_match&&
             !freq_valid&&!freq_busy&&!burst_busy)run_state<=STOPPED;
         else if(wait_count==65535)begin host_errors<=host_errors|32'h80000;run_state<=STOPPED;end
       end
     endcase
     if(s_axi_awvalid&&s_axi_awready)begin wa<=s_axi_awaddr;aw_hold<=1;end
     if(s_axi_wvalid&&s_axi_wready)begin wd<=s_axi_wdata;acknowledgment_data<=s_axi_wdata;ws<=s_axi_wstrb;w_hold<=1;end
     if(s_axi_bvalid&&s_axi_bready)s_axi_bvalid<=0;
     if(write_fire)begin
       aw_hold<=0;w_hold<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
       if(ws==0)begin end
       else if(control_address)begin
         if(strobed_data[2])begin run_state<=RESET_CORE;wait_count<=0;stop_pending<=1;abort_pending<=1;epoch<=epoch+1;host_errors<=host_errors|32'h1000;end
         else if(strobed_data[0])begin
           if(!active&&config_valid&&config_dirty==0&&freq_consumer==freq_producer&&burst_consumer==burst_producer)begin
             run_state<=RESET_CORE;wait_count<=0;stop_pending<=0;abort_pending<=0;epoch<=epoch+1;host_errors<=0;
           end else begin s_axi_bresp<=2;host_errors<=host_errors|32'h200;end
         end
         if(strobed_data[1])stop_pending<=1;
       end
       else if(frequency_ack_address)begin
         if(ws==15&&in_modular_interval(acknowledgment_data,freq_consumer,freq_producer))freq_consumer<=wd;else s_axi_bresp<=2;
       end
       else if(burst_ack_address)begin
         if(ws==15&&in_modular_interval(acknowledgment_data,burst_consumer,burst_producer))burst_consumer<=wd;else s_axi_bresp<=2;
       end
       else if(wa[1:0]!=0)begin s_axi_bresp<=2;host_errors<=host_errors|32'h100;end
       else if(wa>=18'h10000&&wa<18'h30000)begin
         if((active&&host_bank==active_bank)||(pending_valid&&host_bank==pending_bank))begin
           s_axi_bresp<=2;host_errors<=host_errors|32'h100;stream_write_rejected<=stream_write_rejected+1;stream_errors<=stream_errors|1;
         end else if(loader_active&&host_bank==loader_target)begin
           s_axi_bresp<=2;stream_write_rejected<=stream_write_rejected+1;stream_errors<=stream_errors|32'h20;
         end
       end else case(wa)
         'h064:host_errors<=host_errors&~strobed_data;
         'h070:if(!active&&config_valid&&strobed_data[0])begin config_id<=config_id+1;config_dirty<=0;end else begin s_axi_bresp<=2;host_errors<=host_errors|32'h200;end
         'h078:begin
           if(strobed_data[1])snapshot_valid<=0;
           if(strobed_data[0]&&!snapshot_valid&&!snapshot_pending&&!acquisition_reset)begin snap_request<=1;snapshot_pending<=1;end
           else if(strobed_data[0])s_axi_bresp<=2;
         end
         'h100:begin
           if(diagnostic_busy||acquisition_reset) s_axi_bresp<=2;
           else begin
             tick_snapshot<=tick;samples_snapshot<=samples;completed_snapshot<=completed;
             latency_snapshot<=max_latency;publish_snapshot<=publish_latency_max;
             issued_snapshot<=issued;accepted_snapshot<=accepted_samples;rejected_snapshot<=input_rejected;
             high_water_snapshot<=input_high_water;
             diagnostic_toggle<=!diagnostic_toggle;diagnostic_busy<=1;diagnostic_valid<=0;
           end
         end
         'h180:if(wd[31:1]==0)host_bank<=wd[0];else begin s_axi_bresp<=2;stream_errors<=stream_errors|2;end
         'h184:begin
           if(strobed_data[4])begin stream_write_rejected<=0;stream_errors<=0;end
           if(strobed_data[2])pending_valid<=0;
           if(strobed_data[3])begin
             if(!host_bank_clearable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
           end
           if(strobed_data[0])begin
             if(!(host_bank_metadata_valid&&host_bank_writable)) begin s_axi_bresp<=2;stream_errors<=stream_errors|8;end
           end
           if(strobed_data[1])begin
             if(!(host_bank?bank_ready[1]:bank_ready[0])&&!manual_ready)begin s_axi_bresp<=2;stream_errors<=stream_errors|16;end
             else if(active)begin
               if(host_bank==active_bank||pending_valid)begin s_axi_bresp<=2;stream_errors<=stream_errors|16;end
               else begin pending_bank<=host_bank;pending_valid<=1;end
             end else begin active_bank<=host_bank;current_block_id<=host_bank?bank_block1:bank_block0;end
           end
         end
         'h18c:if(!bank0_writable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h190:if(!bank1_writable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h194:if(!bank0_writable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h198:if(!bank1_writable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h19c:if(!bank0_writable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h1a0:if(!bank1_writable)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h1c0:begin
           if(loader_clear)loader_done<=0;
           if(loader_abort)begin loader_active<=0;loader_done<=0;loader_crc_byte<=0;end
           else if(loader_start_request)begin
             if(!loader_start_allowed)s_axi_bresp<=2;
             else begin
               loader_active<=1;loader_done<=0;loader_write_allowed<=1;loader_received<=0;loader_crc_state<=32'hffffffff;
               loader_computed_crc<=0;loader_crc_byte<=0;
             end
           end
           else if(strobed_data[2]&&loader_active)s_axi_bresp<=2;
         end
         'h1c4:if(!loader_active&&wd[31:1]==0)loader_target<=wd[0];else s_axi_bresp<=2;
         'h1c8:if(!loader_active)loader_expected<=merge_bytes(loader_expected,wd,ws);else s_axi_bresp<=2;
         'h1cc:if(!loader_active)loader_block<=merge_bytes(loader_block,wd,ws);else s_axi_bresp<=2;
         'h1d0:if(!loader_active)loader_expected_crc<=merge_bytes(loader_expected_crc,wd,ws);else s_axi_bresp<=2;
         default:if((|config_address)&&!active)config_dirty<=1;
         else begin s_axi_bresp<=2;host_errors<=host_errors|32'h100;end
       endcase
     end
     if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
     if(s_axi_arvalid&&s_axi_arready)begin ra<=s_axi_araddr;read_delay<=1;end
     else if(read_delay!=0)begin
       if(read_delay==2)begin
         read_delay<=3;
         read_mapped<=0;
         read_group[0]<=0;
         case(ra[6:2])
           5'd0:begin read_group[0]<=32'h49514131;read_mapped[0]<=1;end
           5'd1:begin read_group[0]<=iq_build_config::HARDWARE_VERSION;read_mapped[0]<=1;end
           5'd2:begin read_group[0]<={20'd0,config_dirty[0],snapshot_valid,core_ready,active,5'd0,run_state};read_mapped[0]<=1;end
           5'd4:begin read_group[0]<=iq_build_config::SAMPLE_RATE_HZ;read_mapped[0]<=1;end
           5'd5:begin read_group[0]<=iq_build_config::FFT_CLOCK_HZ;read_mapped[0]<=1;end
           5'd6:begin read_group[0]<=N;read_mapped[0]<=1;end
           5'd7:begin read_group[0]<=replay_length;read_mapped[0]<=1;end
           5'd8:begin read_group[0]<=replay_start;read_mapped[0]<=1;end
           5'd9:begin read_group[0]<=replay_mode;read_mapped[0]<=1;end
           5'd10:begin read_group[0]<=window_mode;read_mapped[0]<=1;end
           5'd11:begin read_group[0]<=roi_l;read_mapped[0]<=1;end
           5'd12:begin read_group[0]<=roi_h;read_mapped[0]<=1;end
           5'd13:begin read_group[0]<=ton[31:0];read_mapped[0]<=1;end
           5'd14:begin read_group[0]<={28'd0,ton[35:32]};read_mapped[0]<=1;end
           5'd15:begin read_group[0]<=toff[31:0];read_mapped[0]<=1;end
           5'd16:begin read_group[0]<={28'd0,toff[35:32]};read_mapped[0]<=1;end
           5'd17:begin read_group[0]<={16'd0,kon};read_mapped[0]<=1;end
           5'd18:begin read_group[0]<={16'd0,koff};read_mapped[0]<=1;end
           5'd19:begin read_group[0]<=max_burst;read_mapped[0]<=1;end
           5'd20:begin read_group[0]<=freq_producer;read_mapped[0]<=1;end
           5'd21:begin read_group[0]<=freq_consumer;read_mapped[0]<=1;end
           5'd22:begin read_group[0]<=burst_producer;read_mapped[0]<=1;end
           5'd23:begin read_group[0]<=burst_consumer;read_mapped[0]<=1;end
           5'd24:begin read_group[0]<=error_status;read_mapped[0]<=1;end
           5'd26:begin read_group[0]<=epoch;read_mapped[0]<=1;end
           5'd27:begin read_group[0]<=config_id;read_mapped[0]<=1;end
           5'd31:begin read_group[0]<={30'd0,snapshot_pending,snapshot_valid};read_mapped[0]<=1;end
           default:begin end
         endcase
         read_group[1]<=0;
         case(ra[6:2])
           5'd0:begin read_group[1]<=snapshot_window;read_mapped[1]<=1;end
           5'd1:begin read_group[1]<=detector_mode;read_mapped[1]<=1;end
           5'd2:begin read_group[1]<=gap_min;read_mapped[1]<=1;end
           5'd3:begin read_group[1]<=iq_build_config::CAPABILITIES;read_mapped[1]<=1;end
           5'd4:begin read_group[1]<=iq_build_config::BUILD_ID[0+:32];read_mapped[1]<=1;end
           5'd5:begin read_group[1]<=iq_build_config::BUILD_ID[32+:32];read_mapped[1]<=1;end
           5'd6:begin read_group[1]<=iq_build_config::BUILD_ID[64+:32];read_mapped[1]<=1;end
           5'd7:begin read_group[1]<=iq_build_config::BUILD_ID[96+:32];read_mapped[1]<=1;end
           5'd8:begin read_group[1]<=iq_build_config::TIMESTAMP_CLOCK_HZ;read_mapped[1]<=1;end
           5'd9:begin read_group[1]<=iq_build_config::RECORD_FORMAT_VERSION;read_mapped[1]<=1;end
           5'd10:begin read_group[1]<=iq_build_config::SCAN_LANES;read_mapped[1]<=1;end
           default:begin end
         endcase
         read_group[2]<=0;
         case(ra[6:2])
           5'd4:begin read_group[2]<=tick_snapshot[31:0];read_mapped[2]<=1;end
           5'd5:begin read_group[2]<=tick_snapshot[63:32];read_mapped[2]<=1;end
           5'd6:begin read_group[2]<=samples_snapshot[31:0];read_mapped[2]<=1;end
           5'd7:begin read_group[2]<=samples_snapshot[63:32];read_mapped[2]<=1;end
           5'd8:begin read_group[2]<=completed_snapshot;read_mapped[2]<=1;end
           5'd9:begin read_group[2]<=latency_snapshot;read_mapped[2]<=1;end
           5'd10:begin read_group[2]<=publish_snapshot;read_mapped[2]<=1;end
           5'd11:begin read_group[2]<=freq_dropped;read_mapped[2]<=1;end
           5'd12:begin read_group[2]<=burst_dropped;read_mapped[2]<=1;end
           5'd13:begin read_group[2]<={30'd0,diagnostic_busy,diagnostic_valid};read_mapped[2]<=1;end
           5'd14:begin read_group[2]<=diagnostic_sequence;read_mapped[2]<=1;end
           5'd16:begin read_group[2]<=issued_snapshot[31:0];read_mapped[2]<=1;end
           5'd17:begin read_group[2]<=issued_snapshot[63:32];read_mapped[2]<=1;end
           5'd18:begin read_group[2]<=accepted_snapshot[31:0];read_mapped[2]<=1;end
           5'd19:begin read_group[2]<=accepted_snapshot[63:32];read_mapped[2]<=1;end
           5'd20:begin read_group[2]<=rejected_snapshot;read_mapped[2]<=1;end
           5'd21:begin read_group[2]<={19'd0,high_water_snapshot};read_mapped[2]<=1;end
           5'd22:begin read_group[2]<=diagnostic_arrival_tick[31:0];read_mapped[2]<=1;end
           5'd23:begin read_group[2]<=diagnostic_arrival_tick[63:32];read_mapped[2]<=1;end
           5'd24:begin read_group[2]<=fft_diagnostic_snapshot[0+:32];read_mapped[2]<=1;end
           5'd25:begin read_group[2]<=fft_diagnostic_snapshot[32+:32];read_mapped[2]<=1;end
           5'd26:begin read_group[2]<=fft_diagnostic_snapshot[64+:32];read_mapped[2]<=1;end
           5'd27:begin read_group[2]<=fft_diagnostic_snapshot[96+:32];read_mapped[2]<=1;end
           5'd28:begin read_group[2]<=fft_diagnostic_snapshot[128+:32];read_mapped[2]<=1;end
           5'd29:begin read_group[2]<=fft_diagnostic_snapshot[160+:32];read_mapped[2]<=1;end
           5'd30:begin read_group[2]<=fft_diagnostic_snapshot[192+:32];read_mapped[2]<=1;end
           default:begin end
         endcase
         read_group[3]<=0;
         case(ra[6:2])
           5'd0:begin read_group[3]<={31'd0,host_bank};read_mapped[3]<=1;end
           5'd1:begin read_group[3]<=0;read_mapped[3]<=1;end
           5'd2:begin read_group[3]<={24'd0,(!active||host_bank!=active_bank),active,bank_ready,pending_valid,pending_bank,host_bank,active_bank};read_mapped[3]<=1;end
           5'd3:begin read_group[3]<=bank_length0;read_mapped[3]<=1;end
           5'd4:begin read_group[3]<=bank_length1;read_mapped[3]<=1;end
           5'd5:begin read_group[3]<=bank_block0;read_mapped[3]<=1;end
           5'd6:begin read_group[3]<=bank_block1;read_mapped[3]<=1;end
           5'd7:begin read_group[3]<=bank_crc0;read_mapped[3]<=1;end
           5'd8:begin read_group[3]<=bank_crc1;read_mapped[3]<=1;end
           5'd9:begin read_group[3]<=switch_count;read_mapped[3]<=1;end
           5'd10:begin read_group[3]<=current_block_id;read_mapped[3]<=1;end
           5'd11:begin read_group[3]<=last_switch_tick[31:0];read_mapped[3]<=1;end
           5'd12:begin read_group[3]<=last_switch_tick[63:32];read_mapped[3]<=1;end
           5'd13:begin read_group[3]<=stream_write_rejected;read_mapped[3]<=1;end
           5'd14:begin read_group[3]<=stream_errors;read_mapped[3]<=1;end
           5'd16:begin read_group[3]<=0;read_mapped[3]<=1;end
           5'd17:begin read_group[3]<={31'd0,loader_target};read_mapped[3]<=1;end
           5'd18:begin read_group[3]<=loader_expected;read_mapped[3]<=1;end
           5'd19:begin read_group[3]<=loader_block;read_mapped[3]<=1;end
           5'd20:begin read_group[3]<=loader_expected_crc;read_mapped[3]<=1;end
           5'd21:begin read_group[3]<={28'd0,loader_target,(loader_errors!=0),loader_done,loader_active};read_mapped[3]<=1;end
           5'd22:begin read_group[3]<=loader_received;read_mapped[3]<=1;end
           5'd23:begin read_group[3]<=loader_computed_crc;read_mapped[3]<=1;end
           5'd24:begin read_group[3]<=loader_transfers;read_mapped[3]<=1;end
           5'd25:begin read_group[3]<=loader_errors;read_mapped[3]<=1;end
           5'd26:begin read_group[3]<=32768;read_mapped[3]<=1;end
           5'd27:begin read_group[3]<=FREQ_CAP;read_mapped[3]<=1;end
           5'd28:begin read_group[3]<=128;read_mapped[3]<=1;end
           5'd29:begin read_group[3]<=1024;read_mapped[3]<=1;end
           5'd30:begin read_group[3]<=iq_build_config::INPUT_FIFO_DEPTH;read_mapped[3]<=1;end
           5'd31:begin read_group[3]<=iq_build_config::SNAPSHOT_GROUP;read_mapped[3]<=1;end
           default:begin end
         endcase
       end else if(read_delay==3)begin
         read_delay<=0;s_axi_rvalid<=1;s_axi_rresp<=0;
         if(ra[1:0]!=0)begin s_axi_rdata<=0;s_axi_rresp<=2;end
         else if(ra>=18'h10000&&ra<18'h30000)s_axi_rdata<=host_replay_q;
         else if(ra>=18'h30000&&ra<18'h38000)s_axi_rdata<=freq_read;
         else if(ra>=18'h38000&&ra<18'h3a000)s_axi_rdata<=burst_read;
         else if(ra>=18'h3a000&&ra<18'h3c000)s_axi_rdata<=ra[2]?snapshot_q[63:32]:snapshot_q[31:0];
         else if(ra[17:9]==0&&read_mapped[ra[8:7]])s_axi_rdata<=read_group[ra[8:7]];
         else begin s_axi_rdata<=0;s_axi_rresp<=2;end
       end else read_delay<=read_delay+1;
     end
   end
 end
endmodule
