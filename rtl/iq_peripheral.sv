`timescale 1ns/1ps
// AXI4-Lite control/replay/results. All bus and source logic uses 100 MHz.
module iq_peripheral(
 (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *) input wire s_axi_aclk,
 (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *)
 (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *) input wire s_axi_aresetn,
 (* X_INTERFACE_PARAMETER="FREQ_HZ 125000000" *)
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
 (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready);
 wire clk=s_axi_aclk,rst=!s_axi_aresetn;
 reg aw_hold,w_hold;reg [17:0] wa;reg [31:0] wd;reg [3:0] ws;
 assign s_axi_awready=!aw_hold&&!s_axi_bvalid;
 assign s_axi_wready=!w_hold&&!s_axi_bvalid;
 wire write_fire=aw_hold&&w_hold&&!s_axi_bvalid&&read_delay==0;
 reg [1:0] read_delay;reg [17:0] ra;
 assign s_axi_arready=read_delay==0&&!s_axi_rvalid;
 reg [63:0] tick;
 localparam STOPPED=0,RESET_CORE=1,WAIT_CORE=2,RUNNING=3,DRAINING=4;
 reg [2:0] run_state;reg [15:0] wait_count;reg stop_pending,abort_pending;
 wire active=run_state!=STOPPED;
 wire acquisition_reset=rst||run_state==RESET_CORE;
 reg [31:0] replay_length,replay_start,replay_mode,window_mode,roi_l,roi_h;
 reg [35:0] ton,toff;reg [15:0] kon,koff;reg [31:0] max_burst;
 reg [31:0] epoch,config_id,config_dirty;
 reg [31:0] freq_consumer,burst_consumer,host_errors;
 wire [31:0] freq_producer,burst_producer,freq_dropped,burst_dropped;
 wire freq_busy,burst_busy;
 wire [31:0] freq_read,burst_read;
 wire [7:0] core_errors;
 wire [31:0] error_status=host_errors|{24'd0,core_errors}|(freq_dropped!=0?32'h10000:0)|(burst_dropped!=0?32'h20000:0);
 wire config_ok=replay_length>=8192&&replay_length<=32768&&replay_length[12:0]==0&&
   replay_start<32768&&replay_start+replay_length<=32768&&replay_mode<=1&&window_mode<=1&&
   roi_l<=roi_h&&roi_h<8192&&ton>toff&&kon!=0&&koff!=0&&max_burst>=kon&&max_burst<=1048576;
 reg config_valid;
 always @(posedge clk)if(rst)config_valid<=0;else config_valid<=config_ok;
 reg [63:0] issued;
 reg [14:0] replay_ptr;reg [31:0] replay_pos;
 (* ram_style="block" *) reg [31:0] replay_mem[0:32767];
 reg [31:0] replay_q,host_replay_q;
 reg source_valid,source_finish;
 wire issue=run_state==RUNNING;
 wire final_issue=issue&&((replay_mode==0&&replay_pos==replay_length-1)||
   (stop_pending&&issued[12:0]==8191));
 wire replay_write=write_fire&&wa>=18'h10000&&wa<18'h30000&&!active&&wa[1:0]==0;
 wire [14:0] host_ram_addr=replay_write?((wa-18'h10000)>>2):((ra-18'h10000)>>2);
 integer byte_lane;
 always @(posedge clk)begin
   replay_q<=replay_mem[replay_ptr];host_replay_q<=replay_mem[host_ram_addr];
   if(replay_write)for(byte_lane=0;byte_lane<4;byte_lane=byte_lane+1)
     if(ws[byte_lane])replay_mem[host_ram_addr][byte_lane*8+:8]<=wd[byte_lane*8+:8];
 end
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
   .valid(source_valid),.iq(replay_q),.finish(source_finish),.tick(tick),.hann(window_mode[0]),
   .roi_low(roi_l[12:0]),.roi_high(roi_h[12:0]),.ton(ton),.toff(toff),.kon(kon),.koff(koff),.max_burst(max_burst),
   .epoch(epoch),.config_id(config_id),.ready(core_ready),.fft_reset(fft_reset),.freq_valid(freq_valid),.freq_record(freq_record),
   .burst_valid(burst_valid),.burst_record(burst_record),.samples(samples),.completed(completed),.max_latency(max_latency),
   .errors(core_errors),.snap_request(snap_request),.snap_we(snap_we),.snap_addr(snap_addr),.snap_data(snap_data),.snap_done(snap_done),.snap_window(snap_window));
 record_ring #(.WORDS_LOG2(5),.RECORDS_LOG2(8)) freq_ring(.clk(clk),.rst(acquisition_reset),.push(freq_valid),.record_data(freq_record),
   .consumer(freq_consumer),.producer(freq_producer),.dropped(freq_dropped),.busy(freq_busy),.read_addr(ra[14:2]),.read_data(freq_read));
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
     tick<=0;run_state<=STOPPED;wait_count<=0;stop_pending<=0;abort_pending<=0;issued<=0;replay_ptr<=0;replay_pos<=0;
     source_valid<=0;source_finish<=0;replay_length<=32768;replay_start<=0;replay_mode<=0;window_mode<=1;
     roi_l<=0;roi_h<=8191;ton<=1048576;toff<=262144;kon<=8;koff<=32;max_burst<=1048576;
     epoch<=0;config_id<=1;config_dirty<=0;freq_consumer<=0;burst_consumer<=0;host_errors<=0;
     snap_request<=0;snapshot_valid<=0;snapshot_pending<=0;snapshot_window<=0;
     tick_snapshot<=0;samples_snapshot<=0;completed_snapshot<=0;latency_snapshot<=0;publish_snapshot<=0;
     publish_latency_max<=0;publish_start<=0;freq_busy_previous<=0;
   end else begin
     tick<=tick+1;source_valid<=issue;source_finish<=final_issue;
     freq_busy_previous<=freq_busy;
     if(freq_valid&&!freq_busy&&freq_producer-freq_consumer<256)publish_start<=freq_record[8*32+:64];
     if(freq_busy_previous&&!freq_busy&&tick-publish_start>publish_latency_max)publish_latency_max<=tick-publish_start;
     if(acquisition_reset)begin
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
         if(replay_pos==replay_length-1)begin replay_pos<=0;replay_ptr<=replay_start[14:0];end
         else begin replay_pos<=replay_pos+1;replay_ptr<=replay_ptr+1;end
         if(final_issue)begin run_state<=DRAINING;wait_count<=0;end
         if(core_errors!=0)stop_pending<=1;
       end
       DRAINING:begin
         if(wait_count!=65535)wait_count<=wait_count+1;
         if(wait_count>=1024&&completed==(issued>>13)&&freq_producer+freq_dropped==completed&&
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
         if(active)begin s_axi_bresp<=2;host_errors<=host_errors|32'h100;end
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
         'h100:begin tick_snapshot<=tick;samples_snapshot<=samples;completed_snapshot<=completed;latency_snapshot<=max_latency;publish_snapshot<=publish_latency_max;end
         default:if(wa>=18'h01c&&wa<=18'h04c&&!active)begin
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
           'h004:s_axi_rdata<=32'h00010000;
           'h008:s_axi_rdata<={20'd0,config_dirty[0],snapshot_valid,core_ready,active,5'd0,run_state};
           'h010:s_axi_rdata<=100000000;
           'h014:s_axi_rdata<=125000000;
           'h018:s_axi_rdata<=8192;
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
