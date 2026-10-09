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
 reg [1:0] read_delay;reg [17:0] ra;
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
 reg [31:0] detector_mode,gap_min;
 reg [31:0] epoch,config_id,config_dirty;
 reg [31:0] freq_consumer,burst_consumer,host_errors;
 wire [31:0] freq_producer,burst_producer,freq_dropped,burst_dropped;
 wire freq_busy,burst_busy;
 wire [31:0] freq_read,burst_read;
 wire [7:0] core_errors;
 wire [31:0] error_status=host_errors|{24'd0,core_errors}|(freq_dropped!=0?32'h10000:0)|(burst_dropped!=0?32'h20000:0);
 wire config_ok=replay_length>=N&&replay_length<=32768&&replay_length[LOGN-1:0]==0&&
   replay_start<32768&&replay_start+replay_length<=32768&&replay_mode<=1&&window_mode<=1&&
   roi_l<=roi_h&&roi_h<N&&ton>toff&&kon!=0&&koff!=0&&
   detector_mode<=1&&gap_min>=1&&gap_min<=65535&&
   max_burst>=(detector_mode==1?32'd1:{16'd0,kon})&&max_burst<=1048576;
 reg config_valid;
 always @(posedge clk)if(rst)config_valid<=0;else config_valid<=config_ok;
 reg [63:0] issued;
 reg [14:0] replay_ptr;reg [31:0] replay_pos;
 reg host_bank,active_bank,pending_bank,pending_valid;
 reg [1:0] bank_ready;
 reg [31:0] bank_length0,bank_length1,bank_block0,bank_block1,bank_crc0,bank_crc1;
 reg [31:0] current_block_id,switch_count,stream_write_rejected,stream_errors;
 reg [63:0] last_switch_tick;
 reg loader_target,loader_active,loader_done;
 reg loader_write_allowed;
 reg [31:0] loader_expected,loader_block,loader_expected_crc,loader_received;
 reg [31:0] loader_crc_state,loader_computed_crc,loader_transfers,loader_errors;
 reg [31:0] loader_word;reg [3:0] loader_word_keep;reg loader_word_last;reg [2:0] loader_crc_byte;
 wire [31:0] host_bank_length=host_bank?bank_length1:bank_length0;
 wire host_bank_metadata_valid=host_bank_length>=N&&host_bank_length<=32768&&
   host_bank_length[LOGN-1:0]==0&&host_bank_length==replay_length;
 function automatic [31:0] crc32_byte(input [31:0] crc,input [7:0] data);
   reg [31:0] c;integer bit_index;
   begin
     c=crc^data;
     for(bit_index=0;bit_index<8;bit_index=bit_index+1)c=(c>>1)^(32'hedb88320&{32{c[0]}});
     crc32_byte=c;
   end
 endfunction
 wire dma_fire=s_axis_iq_tvalid&&s_axis_iq_tready;
 wire [31:0] dma_crc_next=crc32_byte(loader_crc_state,loader_word[(loader_crc_byte-1)*8+:8]);
 wire [31:0] loader_word_errors=(loader_word_keep!=4'hf ? 32'h2 : 0)|
   (loader_received>=loader_expected ? 32'h4 : 0)|
   (loader_received+1==loader_expected&&!loader_word_last ? 32'h8 : 0);
 // CRC processing leaves four clocks between accepted AXIS words. Prepare
 // the NEXT word's range check before received advances, keeping the wide
 // comparison out of the BRAM write-enable fanout path. Error accounting
 // still uses the full 32-bit counters, including malformed overlong blocks.
 wire dma_loader_write=dma_fire&&loader_write_allowed&&s_axis_iq_tkeep==4'hf;
 assign s_axis_iq_tready=loader_active&&loader_crc_byte==0;
 wire [31:0] replay_q,host_replay_q;
 wire [31:0] replay_q0,replay_q1,host_replay_q0,host_replay_q1;
 reg [31:0] core_iq;
 reg source_valid,source_finish,core_valid,core_finish;
 reg [63:0] core_tick;
 wire issue=run_state==RUNNING;
 wire final_issue=issue&&((replay_mode==0&&replay_pos==replay_length-1)||
   (stop_pending&&issued[LOGN-1:0]==N-1));
 wire bank0_writable=(!active||active_bank!=0)&&(!pending_valid||pending_bank!=0)&&(!loader_active||loader_target!=0);
 wire bank1_writable=(!active||active_bank!=1)&&(!pending_valid||pending_bank!=1)&&(!loader_active||loader_target!=1);
 wire replay_write=write_fire&&wa>=18'h10000&&wa<18'h30000&&wa[1:0]==0&&
   (host_bank?bank1_writable:bank0_writable);
 wire [14:0] host_ram_addr=replay_write?((wa-18'h10000)>>2):((ra-18'h10000)>>2);
 wire [14:0] bank_host_addr=dma_loader_write?loader_received[14:0]:host_ram_addr;
 wire [31:0] bank_host_wdata=dma_loader_write?s_axis_iq_tdata:wd;
 wire [3:0] bank_host_wstrb=dma_loader_write?4'hf:ws;
 assign replay_q=active_bank?replay_q1:replay_q0;
 assign host_replay_q=host_bank?host_replay_q1:host_replay_q0;
 iq_replay_bank bank0(.clk(clk),.host_addr(bank_host_addr),
   .host_we((replay_write&&!host_bank)||(dma_loader_write&&!loader_target)),
   .host_wstrb(bank_host_wstrb),.host_wdata(bank_host_wdata),.host_q(host_replay_q0),.replay_addr(replay_ptr),.replay_q(replay_q0));
 iq_replay_bank bank1(.clk(clk),.host_addr(bank_host_addr),
   .host_we((replay_write&&host_bank)||(dma_loader_write&&loader_target)),
   .host_wstrb(bank_host_wstrb),.host_wdata(bank_host_wdata),.host_q(host_replay_q1),.replay_addr(replay_ptr),.replay_q(replay_q1));
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
   .roi_low(roi_l[LOGN-1:0]),.roi_high(roi_h[LOGN-1:0]),.ton(ton),.toff(toff),.kon(kon),.koff(koff),.max_burst(max_burst),
   .detector_mode(detector_mode[0]),.gap_min(gap_min[15:0]),
   .epoch(epoch),.config_id(config_id),.ready(core_ready),.fft_reset(fft_reset),.freq_valid(freq_valid),.freq_record(freq_record),
   .burst_valid(burst_valid),.burst_record(burst_record),.samples(samples),.completed(completed),.max_latency(max_latency),
   .errors(core_errors),.snap_request(snap_request),.snap_we(snap_we),.snap_addr(snap_addr),.snap_data(snap_data),.snap_done(snap_done),.snap_window(snap_window));
 record_ring #(.WORDS_LOG2(5),.RECORDS_LOG2(FREQ_LOG)) freq_ring(.clk(clk),.rst(acquisition_reset),.push(freq_valid),.record_data(freq_record),
   .consumer(freq_consumer),.producer(freq_producer),.dropped(freq_dropped),.busy(freq_busy),.read_addr(ra[FREQ_LOG+6:2]),.read_data(freq_read));
 record_ring #(.WORDS_LOG2(4),.RECORDS_LOG2(7)) burst_ring(.clk(clk),.rst(acquisition_reset),.push(burst_valid),.record_data(burst_record),
   .consumer(burst_consumer),.producer(burst_producer),.dropped(burst_dropped),.busy(burst_busy),.read_addr(ra[12:2]),.read_data(burst_read));
 function automatic [31:0] merge_bytes(input [31:0] old_value,new_value,input [3:0] strb);
   integer b;begin for(b=0;b<4;b=b+1)merge_bytes[b*8+:8]=strb[b]?new_value[b*8+:8]:old_value[b*8+:8];end
 endfunction
 wire [31:0] strobed_data=merge_bytes(0,wd,ws);
 reg [63:0] tick_snapshot,samples_snapshot;
 reg [31:0] completed_snapshot,latency_snapshot,publish_snapshot;
 always @(posedge clk)begin
   if(rst)begin
     aw_hold<=0;w_hold<=0;wa<=0;wd<=0;ws<=0;s_axi_bvalid<=0;s_axi_bresp<=0;
     s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;read_delay<=0;ra<=0;
     diagnostic_toggle<=0;diagnostic_busy<=0;diagnostic_valid<=0;diagnostic_sequence<=0;
     issued_snapshot<=0;accepted_snapshot<=0;rejected_snapshot<=0;high_water_snapshot<=0;
     fft_diagnostic_snapshot<=0;diagnostic_arrival_tick<=0;
     tick<=0;run_state<=STOPPED;wait_count<=0;stop_pending<=0;abort_pending<=0;issued<=0;replay_ptr<=0;replay_pos<=0;
     host_bank<=0;active_bank<=0;pending_bank<=0;pending_valid<=0;bank_ready<=0;
     bank_length0<=0;bank_length1<=0;bank_block0<=0;bank_block1<=0;bank_crc0<=0;bank_crc1<=0;
     current_block_id<=0;switch_count<=0;stream_write_rejected<=0;stream_errors<=0;last_switch_tick<=0;
     loader_target<=0;loader_active<=0;loader_done<=0;loader_write_allowed<=0;loader_expected<=0;loader_block<=0;loader_expected_crc<=0;
     loader_received<=0;loader_crc_state<=32'hffffffff;loader_computed_crc<=0;loader_transfers<=0;loader_errors<=0;
     loader_word<=0;loader_word_keep<=0;loader_word_last<=0;loader_crc_byte<=0;
     source_valid<=0;source_finish<=0;core_valid<=0;core_finish<=0;core_iq<=0;core_tick<=0;
     replay_length<=32768;replay_start<=0;replay_mode<=0;window_mode<=1;
     roi_l<=0;roi_h<=N-1;ton<=1048576;toff<=262144;kon<=8;koff<=32;max_burst<=1048576;
     detector_mode<=0;gap_min<=32;
     epoch<=0;config_id<=1;config_dirty<=0;freq_consumer<=0;burst_consumer<=0;host_errors<=0;
     snap_request<=0;snapshot_valid<=0;snapshot_pending<=0;snapshot_window<=0;
     tick_snapshot<=0;samples_snapshot<=0;completed_snapshot<=0;latency_snapshot<=0;publish_snapshot<=0;
     publish_latency_max<=0;publish_start<=0;freq_busy_previous<=0;
   end else begin
     if(dma_fire)begin
       loader_word<=s_axis_iq_tdata;loader_word_keep<=s_axis_iq_tkeep;
       loader_word_last<=s_axis_iq_tlast;loader_crc_byte<=1;
     end
     if(loader_crc_byte!=0)begin
       loader_crc_state<=dma_crc_next;
       if(loader_crc_byte==3)loader_write_allowed<=(loader_received+32'd1)<loader_expected;
       if(loader_crc_byte==4)begin
         loader_crc_byte<=0;loader_received<=loader_received+1;
         if(loader_word_errors!=0)loader_errors<=loader_errors|loader_word_errors;
       if(loader_word_last)begin
         loader_active<=0;loader_computed_crc<=dma_crc_next^32'hffffffff;
         if(loader_received+1==loader_expected&&loader_word_keep==4'hf&&
             loader_errors==0&&(dma_crc_next^32'hffffffff)==loader_expected_crc)begin
           loader_done<=1;loader_transfers<=loader_transfers+1;
           if(loader_target)begin
             bank_length1<=loader_expected;bank_block1<=loader_block;bank_crc1<=loader_expected_crc;bank_ready[1]<=1;
           end else begin
             bank_length0<=loader_expected;bank_block0<=loader_block;bank_crc0<=loader_expected_crc;bank_ready[0]<=1;
           end
         end else begin
           loader_errors<=loader_errors|loader_word_errors|
             (loader_received+1!=loader_expected ? 32'h1 : 0)|
             ((dma_crc_next^32'hffffffff)!=loader_expected_crc ? 32'h10 : 0);
           if(loader_target)bank_ready[1]<=0;else bank_ready[0]<=0;
         end
       end
       end else loader_crc_byte<=loader_crc_byte+1;
     end
     if(diagnostic_arrived&&diagnostic_busy)begin
       fft_diagnostic_snapshot<=fft_diagnostic;diagnostic_busy<=0;diagnostic_valid<=1;
       diagnostic_arrival_tick<=tick;diagnostic_sequence<=diagnostic_sequence+1;
     end
     tick<=tick+1;source_valid<=issue;source_finish<=final_issue;
     core_iq<=replay_q;core_valid<=source_valid;core_finish<=source_finish;core_tick<=tick;
     freq_busy_previous<=freq_busy;
     if(freq_valid&&!freq_busy&&freq_producer-freq_consumer<FREQ_CAP)publish_start<=freq_record[8*32+:64];
     if(freq_busy_previous&&!freq_busy&&tick-publish_start>publish_latency_max)publish_latency_max<=tick-publish_start;
     if(acquisition_reset)begin
       diagnostic_toggle<=0;diagnostic_busy<=0;diagnostic_valid<=0;
       freq_consumer<=0;burst_consumer<=0;publish_latency_max<=0;freq_busy_previous<=0;
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
           if(active_bank)bank_ready[1]<=0;else bank_ready[0]<=0;
           switch_count<=switch_count+1;last_switch_tick<=tick;
         end else if(replay_pos==replay_length-1)begin replay_pos<=0;replay_ptr<=replay_start[14:0];end
         else begin replay_pos<=replay_pos+1;replay_ptr<=replay_ptr+1;end
         if(final_issue)begin run_state<=DRAINING;wait_count<=0;end
         if(core_errors!=0)stop_pending<=1;
       end
       DRAINING:begin
         if(wait_count!=65535)wait_count<=wait_count+1;
         if(wait_count>=1024&&completed==(issued>>LOGN)&&freq_producer+freq_dropped==completed&&
             !freq_valid&&!freq_busy&&!burst_busy)run_state<=STOPPED;
         else if(wait_count==65535)begin host_errors<=host_errors|32'h80000;run_state<=STOPPED;end
       end
     endcase
     if(s_axi_awvalid&&s_axi_awready)begin wa<=s_axi_awaddr;aw_hold<=1;end
     if(s_axi_wvalid&&s_axi_wready)begin wd<=s_axi_wdata;ws<=s_axi_wstrb;w_hold<=1;end
     if(s_axi_bvalid&&s_axi_bready)s_axi_bvalid<=0;
     if(write_fire)begin
       aw_hold<=0;w_hold<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
       if(ws==0)begin end
       else if(wa[1:0]!=0)begin s_axi_bresp<=2;host_errors<=host_errors|32'h100;end
       else if(wa>=18'h10000&&wa<18'h30000)begin
         if((active&&host_bank==active_bank)||(pending_valid&&host_bank==pending_bank))begin
           s_axi_bresp<=2;host_errors<=host_errors|32'h100;stream_write_rejected<=stream_write_rejected+1;stream_errors<=stream_errors|1;
         end else if(loader_active&&host_bank==loader_target)begin
           s_axi_bresp<=2;stream_write_rejected<=stream_write_rejected+1;stream_errors<=stream_errors|32'h20;
         end else if(host_bank)bank_ready[1]<=0;else bank_ready[0]<=0;
       end else case(wa)
         'h00c:begin
           if(strobed_data[2])begin run_state<=RESET_CORE;wait_count<=0;stop_pending<=1;abort_pending<=1;epoch<=epoch+1;host_errors<=host_errors|32'h1000;end
           else if(strobed_data[0])begin
             if(!active&&config_valid&&config_dirty==0&&freq_consumer==freq_producer&&burst_consumer==burst_producer)begin
               run_state<=RESET_CORE;wait_count<=0;stop_pending<=0;abort_pending<=0;epoch<=epoch+1;host_errors<=0;
             end else begin s_axi_bresp<=2;host_errors<=host_errors|32'h200;end
           end
           if(strobed_data[1])stop_pending<=1;
         end
         'h054:if(ws==15&&(wd-freq_consumer)<=(freq_producer-freq_consumer))freq_consumer<=wd;else s_axi_bresp<=2;
         'h05c:if(ws==15&&(wd-burst_consumer)<=(burst_producer-burst_consumer))burst_consumer<=wd;else s_axi_bresp<=2;
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
             if(active&&host_bank==active_bank)begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
             else if(host_bank)bank_ready[1]<=0;else bank_ready[0]<=0;
           end
           if(strobed_data[0])begin
             if(host_bank_metadata_valid)begin
               if(host_bank)bank_ready[1]<=1;else bank_ready[0]<=1;
             end else begin s_axi_bresp<=2;stream_errors<=stream_errors|8;end
           end
           if(strobed_data[1])begin
             if(!(host_bank?bank_ready[1]:bank_ready[0])&&!(strobed_data[0]&&host_bank_metadata_valid))begin s_axi_bresp<=2;stream_errors<=stream_errors|16;end
             else if(active)begin
               if(host_bank==active_bank||pending_valid)begin s_axi_bresp<=2;stream_errors<=stream_errors|16;end
               else begin pending_bank<=host_bank;pending_valid<=1;end
             end else begin active_bank<=host_bank;current_block_id<=host_bank?bank_block1:bank_block0;end
           end
         end
         'h18c:if(bank0_writable)bank_length0<=merge_bytes(bank_length0,wd,ws);else begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h190:if(bank1_writable)bank_length1<=merge_bytes(bank_length1,wd,ws);else begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h194:if(bank0_writable)bank_block0<=merge_bytes(bank_block0,wd,ws);else begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h198:if(bank1_writable)bank_block1<=merge_bytes(bank_block1,wd,ws);else begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h19c:if(bank0_writable)bank_crc0<=merge_bytes(bank_crc0,wd,ws);else begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h1a0:if(bank1_writable)bank_crc1<=merge_bytes(bank_crc1,wd,ws);else begin s_axi_bresp<=2;stream_errors<=stream_errors|4;end
         'h1c0:begin
           if(strobed_data[2])begin loader_done<=0;loader_errors<=0;end
           if(strobed_data[1])begin
             loader_active<=0;loader_done<=0;loader_crc_byte<=0;loader_errors<=loader_errors|32'h20;
             if(loader_target)bank_ready[1]<=0;else bank_ready[0]<=0;
           end
           if(strobed_data[0])begin
             if(loader_active||(active&&loader_target==active_bank)||(pending_valid&&loader_target==pending_bank)||loader_expected<N||
                 loader_expected>32768||loader_expected[LOGN-1:0]!=0)begin
               s_axi_bresp<=2;loader_errors<=loader_errors|32'h40;
             end else begin
               loader_active<=1;loader_done<=0;loader_write_allowed<=1;loader_received<=0;loader_crc_state<=32'hffffffff;
               loader_computed_crc<=0;loader_errors<=0;loader_crc_byte<=0;
               if(loader_target)bank_ready[1]<=0;else bank_ready[0]<=0;
             end
           end
         end
         'h1c4:if(!loader_active&&wd[31:1]==0)loader_target<=wd[0];else begin s_axi_bresp<=2;loader_errors<=loader_errors|32'h80;end
         'h1c8:if(!loader_active)loader_expected<=merge_bytes(loader_expected,wd,ws);else s_axi_bresp<=2;
         'h1cc:if(!loader_active)loader_block<=merge_bytes(loader_block,wd,ws);else s_axi_bresp<=2;
         'h1d0:if(!loader_active)loader_expected_crc<=merge_bytes(loader_expected_crc,wd,ws);else s_axi_bresp<=2;
         default:if(((wa>=18'h01c&&wa<=18'h04c)||wa==18'h084||wa==18'h088)&&!active)begin
           config_dirty<=1;
           case(wa)
             'h01c:replay_length<=merge_bytes(replay_length,wd,ws);
             'h020:replay_start<=merge_bytes(replay_start,wd,ws);
             'h024:replay_mode<=merge_bytes(replay_mode,wd,ws);
             'h028:window_mode<=merge_bytes(window_mode,wd,ws);
             'h02c:roi_l<=merge_bytes(roi_l,wd,ws);
             'h030:roi_h<=merge_bytes(roi_h,wd,ws);
             'h034:ton[31:0]<=merge_bytes(ton[31:0],wd,ws);
             'h038:if(ws[0])ton[35:32]<=wd[3:0];
             'h03c:toff[31:0]<=merge_bytes(toff[31:0],wd,ws);
             'h040:if(ws[0])toff[35:32]<=wd[3:0];
             'h044:kon<=merge_bytes({16'd0,kon},wd,ws);
             'h048:koff<=merge_bytes({16'd0,koff},wd,ws);
             'h04c:max_burst<=merge_bytes(max_burst,wd,ws);
             'h084:detector_mode<=merge_bytes(detector_mode,wd,ws);
             'h088:gap_min<=merge_bytes(gap_min,wd,ws);
             default:s_axi_bresp<=2;
           endcase
         end else begin s_axi_bresp<=2;host_errors<=host_errors|32'h100;end
       endcase
     end
     if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
     if(s_axi_arvalid&&s_axi_arready)begin ra<=s_axi_araddr;read_delay<=1;end
     else if(read_delay!=0)begin
       if(read_delay==2)begin
         read_delay<=0;s_axi_rvalid<=1;s_axi_rresp<=0;
         if(ra[1:0]!=0)begin s_axi_rdata<=0;s_axi_rresp<=2;end
         else if(ra>=18'h10000&&ra<18'h30000)s_axi_rdata<=host_replay_q;
         else if(ra>=18'h30000&&ra<18'h38000)s_axi_rdata<=freq_read;
         else if(ra>=18'h38000&&ra<18'h3a000)s_axi_rdata<=burst_read;
         else if(ra>=18'h3a000&&ra<18'h3c000)s_axi_rdata<=ra[2]?snapshot_q[63:32]:snapshot_q[31:0];
         else case(ra)
           'h000:s_axi_rdata<=32'h49514131;
           'h004:s_axi_rdata<=iq_build_config::HARDWARE_VERSION;
           'h008:s_axi_rdata<={20'd0,config_dirty[0],snapshot_valid,core_ready,active,5'd0,run_state};
           'h010:s_axi_rdata<=iq_build_config::SAMPLE_RATE_HZ;
           'h014:s_axi_rdata<=iq_build_config::FFT_CLOCK_HZ;
           'h018:s_axi_rdata<=N;
           'h01c:s_axi_rdata<=replay_length;
           'h020:s_axi_rdata<=replay_start;
           'h024:s_axi_rdata<=replay_mode;
           'h028:s_axi_rdata<=window_mode;
           'h02c:s_axi_rdata<=roi_l;
           'h030:s_axi_rdata<=roi_h;
           'h034:s_axi_rdata<=ton[31:0];'h038:s_axi_rdata<={28'd0,ton[35:32]};
           'h03c:s_axi_rdata<=toff[31:0];'h040:s_axi_rdata<={28'd0,toff[35:32]};
           'h044:s_axi_rdata<={16'd0,kon};'h048:s_axi_rdata<={16'd0,koff};
           'h04c:s_axi_rdata<=max_burst;
           'h050:s_axi_rdata<=freq_producer;'h054:s_axi_rdata<=freq_consumer;
           'h058:s_axi_rdata<=burst_producer;'h05c:s_axi_rdata<=burst_consumer;
           'h060:s_axi_rdata<=error_status;
           'h068:s_axi_rdata<=epoch;'h06c:s_axi_rdata<=config_id;
           'h07c:s_axi_rdata<={30'd0,snapshot_pending,snapshot_valid};
           'h080:s_axi_rdata<=snapshot_window;
           'h084:s_axi_rdata<=detector_mode;
           'h088:s_axi_rdata<=gap_min;
           'h08c:s_axi_rdata<=iq_build_config::CAPABILITIES;
           'h090:s_axi_rdata<=iq_build_config::BUILD_ID[0+:32];
           'h094:s_axi_rdata<=iq_build_config::BUILD_ID[32+:32];
           'h098:s_axi_rdata<=iq_build_config::BUILD_ID[64+:32];
           'h09c:s_axi_rdata<=iq_build_config::BUILD_ID[96+:32];

           'h0a0:s_axi_rdata<=iq_build_config::TIMESTAMP_CLOCK_HZ;
           'h0a4:s_axi_rdata<=iq_build_config::RECORD_FORMAT_VERSION;
           'h0a8:s_axi_rdata<=iq_build_config::SCAN_LANES;
           'h180:s_axi_rdata<={31'd0,host_bank};
           'h184:s_axi_rdata<=0;
           'h188:s_axi_rdata<={24'd0,(!active||host_bank!=active_bank),active,bank_ready,pending_valid,pending_bank,host_bank,active_bank};
           'h18c:s_axi_rdata<=bank_length0;'h190:s_axi_rdata<=bank_length1;
           'h194:s_axi_rdata<=bank_block0;'h198:s_axi_rdata<=bank_block1;
           'h19c:s_axi_rdata<=bank_crc0;'h1a0:s_axi_rdata<=bank_crc1;
           'h1a4:s_axi_rdata<=switch_count;'h1a8:s_axi_rdata<=current_block_id;
           'h1ac:s_axi_rdata<=last_switch_tick[31:0];'h1b0:s_axi_rdata<=last_switch_tick[63:32];
           'h1b4:s_axi_rdata<=stream_write_rejected;'h1b8:s_axi_rdata<=stream_errors;
           'h1c0:s_axi_rdata<=0;'h1c4:s_axi_rdata<={31'd0,loader_target};
           'h1c8:s_axi_rdata<=loader_expected;'h1cc:s_axi_rdata<=loader_block;
           'h1d0:s_axi_rdata<=loader_expected_crc;
           'h1d4:s_axi_rdata<={28'd0,loader_target,(loader_errors!=0),loader_done,loader_active};
           'h1d8:s_axi_rdata<=loader_received;'h1dc:s_axi_rdata<=loader_computed_crc;
           'h1e0:s_axi_rdata<=loader_transfers;'h1e4:s_axi_rdata<=loader_errors;
           'h1e8:s_axi_rdata<=32768;
           'h1ec:s_axi_rdata<=FREQ_CAP;
           'h1f0:s_axi_rdata<=128;
           'h1f4:s_axi_rdata<=1024;
           'h1f8:s_axi_rdata<=iq_build_config::INPUT_FIFO_DEPTH;
           'h1fc:s_axi_rdata<=iq_build_config::SNAPSHOT_GROUP;
           'h134:s_axi_rdata<={30'd0,diagnostic_busy,diagnostic_valid};
           'h138:s_axi_rdata<=diagnostic_sequence;
           'h140:s_axi_rdata<=issued_snapshot[31:0];'h144:s_axi_rdata<=issued_snapshot[63:32];
           'h148:s_axi_rdata<=accepted_snapshot[31:0];'h14c:s_axi_rdata<=accepted_snapshot[63:32];
           'h150:s_axi_rdata<=rejected_snapshot;'h154:s_axi_rdata<={19'd0,high_water_snapshot};
           'h158:s_axi_rdata<=diagnostic_arrival_tick[31:0];'h15c:s_axi_rdata<=diagnostic_arrival_tick[63:32];
           'h160:s_axi_rdata<=fft_diagnostic_snapshot[0+:32];
           'h164:s_axi_rdata<=fft_diagnostic_snapshot[32+:32];
           'h168:s_axi_rdata<=fft_diagnostic_snapshot[64+:32];
           'h16c:s_axi_rdata<=fft_diagnostic_snapshot[96+:32];
           'h170:s_axi_rdata<=fft_diagnostic_snapshot[128+:32];
           'h174:s_axi_rdata<=fft_diagnostic_snapshot[160+:32];
           'h178:s_axi_rdata<=fft_diagnostic_snapshot[192+:32];

           'h110:s_axi_rdata<=tick_snapshot[31:0];'h114:s_axi_rdata<=tick_snapshot[63:32];
           'h118:s_axi_rdata<=samples_snapshot[31:0];'h11c:s_axi_rdata<=samples_snapshot[63:32];
           'h120:s_axi_rdata<=completed_snapshot;'h124:s_axi_rdata<=latency_snapshot;
           'h128:s_axi_rdata<=publish_snapshot;'h12c:s_axi_rdata<=freq_dropped;'h130:s_axi_rdata<=burst_dropped;
           default:begin s_axi_rdata<=0;s_axi_rresp<=2;end
         endcase
       end else read_delay<=read_delay+1;
     end
   end
 end
endmodule
