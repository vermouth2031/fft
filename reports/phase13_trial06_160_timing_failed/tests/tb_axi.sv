`timescale 1ns/1ps
module tb_axi;
 localparam integer N=iq_build_config::FFT_LENGTH,LOGN=iq_build_config::FFT_LOG2;
 reg clk=0,fft_clk=0;
 localparam realtime SRC_HALF_NS=500000000.0/iq_build_config::SAMPLE_RATE_HZ;
 localparam realtime FFT_HALF_NS=500000000.0/iq_build_config::FFT_CLOCK_HZ;
 localparam integer TONE_HZ=iq_build_config::SAMPLE_RATE_HZ/4;
 localparam integer HANN_TONE_WIDTH_HZ=(2*iq_build_config::SAMPLE_RATE_HZ+N/2)/N;
 always #(SRC_HALF_NS) clk=~clk;always #(FFT_HALF_NS) fft_clk=~fft_clk;
 reg resetn=0;reg [17:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
 reg [31:0] wdata=0;reg [3:0] wstrb=15;
 wire awready,wready,bvalid,arready,rvalid;wire [1:0] bresp,rresp;wire [31:0] rdata;
 reg [31:0] axis_data=0;reg [3:0] axis_keep=15;reg axis_valid=0,axis_last=0;wire axis_ready;
 // Exercise the precomputed BRAM guard on every valid/invalid DMA word.
 always @(posedge clk)if(resetn&&dut.dma_fire)
   if(dut.loader_write_allowed!==(dut.loader_received<dut.loader_expected))
     $fatal(1,"DMA precomputed range check disagrees with full counter comparison");
 always @(posedge clk)if(resetn&&dut.commit_busy)begin
   if(!dut.loader_active||axis_ready)$fatal(1,"terminal DMA lost ownership");
   if(dut.loader_target?dut.bank1_writable:dut.bank0_writable)$fatal(1,"terminal bank writable");
 end
 always @(posedge clk)if(resetn&&dut.issue)begin
   if(dut.max_burst>1048576||dut.max_burst==0||{11'd0,dut.core_max_burst}!==dut.max_burst)
     $fatal(1,"local burst limit differs from legal acquisition configuration");
 end
 always @(posedge clk)if(resetn&&dut.w_hold)
   if(dut.acknowledgment_data!==dut.wd)$fatal(1,"Acknowledgment data copy mismatch");
 always @(posedge clk)if(resetn&&dut.aw_hold)begin
   if(dut.config_address[0] !== (dut.wa==18'h01c))$fatal(1,"AW predecode mismatch 01c");
   if(dut.config_address[1] !== (dut.wa==18'h020))$fatal(1,"AW predecode mismatch 020");
   if(dut.config_address[2] !== (dut.wa==18'h024))$fatal(1,"AW predecode mismatch 024");
   if(dut.config_address[3] !== (dut.wa==18'h028))$fatal(1,"AW predecode mismatch 028");
   if(dut.config_address[4] !== (dut.wa==18'h02c))$fatal(1,"AW predecode mismatch 02c");
   if(dut.config_address[5] !== (dut.wa==18'h030))$fatal(1,"AW predecode mismatch 030");
   if(dut.config_address[6] !== (dut.wa==18'h034))$fatal(1,"AW predecode mismatch 034");
   if(dut.config_address[7] !== (dut.wa==18'h038))$fatal(1,"AW predecode mismatch 038");
   if(dut.config_address[8] !== (dut.wa==18'h03c))$fatal(1,"AW predecode mismatch 03c");
   if(dut.config_address[9] !== (dut.wa==18'h040))$fatal(1,"AW predecode mismatch 040");
   if(dut.config_address[10] !== (dut.wa==18'h044))$fatal(1,"AW predecode mismatch 044");
   if(dut.config_address[11] !== (dut.wa==18'h048))$fatal(1,"AW predecode mismatch 048");
   if(dut.config_address[12] !== (dut.wa==18'h04c))$fatal(1,"AW predecode mismatch 04c");
   if(dut.config_address[13] !== (dut.wa==18'h084))$fatal(1,"AW predecode mismatch 084");
   if(dut.config_address[14] !== (dut.wa==18'h088))$fatal(1,"AW predecode mismatch 088");
 end
 // Independent issued-sample scoreboard: each accepted read must emerge
 // from the same bank/address two source registers later, even at a switch.
 reg [31:0] expected_replay_1,expected_replay_2;
 reg expected_valid_1=0,expected_valid_2=0;
 integer replay_checked=0,replay_switches=0;
 reg previous_issue_bank=0;
 always @(posedge clk)begin
   if(!resetn)begin expected_valid_1<=0;expected_valid_2<=0;previous_issue_bank<=0;end
   else begin
     if(dut.core_valid!==expected_valid_2)$fatal(1,"Replay valid pipeline mismatch");
     if(dut.core_valid)begin
       if(dut.core_iq!==expected_replay_2)$fatal(1,"Replay bank/address alignment mismatch got=%h expected=%h",dut.core_iq,expected_replay_2);
       replay_checked=replay_checked+1;
     end
     expected_valid_1<=dut.issue;expected_valid_2<=expected_valid_1;
     expected_replay_2<=expected_replay_1;
     if(dut.issue)begin
       expected_replay_1<=dut.active_bank?dut.bank1.mem[dut.replay_ptr]:dut.bank0.mem[dut.replay_ptr];
       if(dut.active_bank!=previous_issue_bank)replay_switches=replay_switches+1;
       previous_issue_bank<=dut.active_bank;
       if({dut.bank1_replay_en,dut.bank0_replay_en}!==(dut.active_bank?2'b10:2'b01))
         $fatal(1,"Replay must enable exactly the issuing bank");
     end else if(dut.bank0_replay_en||dut.bank1_replay_en)$fatal(1,"Idle replay port enabled");
   end
 end
 iq_peripheral dut(.s_axi_aclk(clk),.s_axi_aresetn(resetn),.fft_clk(fft_clk),
 .s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
 .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
 .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
 .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
 .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
 .s_axis_iq_tdata(axis_data),.s_axis_iq_tkeep(axis_keep),.s_axis_iq_tvalid(axis_valid),
 .s_axis_iq_tready(axis_ready),.s_axis_iq_tlast(axis_last));
 function automatic [31:0] crc_word(input [31:0] crc,input [31:0] data);
   reg [31:0] c;integer b,k;
   begin c=crc;for(b=0;b<4;b=b+1)begin c=c^data[b*8+:8];for(k=0;k<8;k=k+1)c=(c>>1)^(32'hedb88320&{32{c[0]}});end crc_word=c;end
 endfunction
 task axis_send(input [31:0] data,input last);
   begin
     @(negedge clk);axis_data=data;axis_keep=15;axis_last=last;axis_valid=1;
     do @(posedge clk);while(!axis_ready);
     @(negedge clk);axis_valid=0;axis_last=0;
   end
 endtask
 task wr(input [17:0] addr,input [31:0] value,input [3:0] strobe,input integer skew,input [1:0] expected);
   begin
     fork
       begin
         repeat(skew>0?skew:0)@(negedge clk);
         @(negedge clk);awaddr=addr;awvalid=1;
         do @(posedge clk);while(!awready);
         @(negedge clk);awvalid=0;
       end
       begin
         repeat(skew<0?-skew:0)@(negedge clk);
         @(negedge clk);wdata=value;wstrb=strobe;wvalid=1;
         do @(posedge clk);while(!wready);
         @(negedge clk);wvalid=0;
       end
     join
     wait(bvalid);
     repeat(4)begin @(negedge clk);if(!bvalid||bresp!==expected)$fatal(1,"write response addr=%h got=%h expected=%h",addr,bresp,expected);end
     bready=1;@(negedge clk);bready=0;
   end
 endtask
 task rd(input [17:0] addr,output [31:0] value,input [1:0] expected);
   begin
     @(negedge clk);araddr=addr;arvalid=1;
     do @(posedge clk);while(!arready);
     @(negedge clk);arvalid=0;wait(rvalid);value=rdata;
     repeat(3)begin @(negedge clk);if(!rvalid||rdata!==value||rresp!==expected)$fatal(1,"read hold/response addr=%h",addr);end
     rready=1;@(negedge clk);rready=0;
   end
 endtask
 reg [31:0] ack_first,ack_last,ack_value,ack_delta,ack_span;
 integer ack_case;
 integer n,j;reg [31:0] value,producer,dma_crc;reg [31:0] records[0:31];
 initial begin
   for(ack_case=0;ack_case<65536;ack_case=ack_case+1)begin
     ack_first=(ack_case<32768?32'hffff0000:32'h7fff0000)+ack_case;
     ack_last=ack_first+(ack_case%513)-256;
     case(ack_case%8)
       0:ack_value=ack_first-1;1:ack_value=ack_first;2:ack_value=ack_first+1;
       3:ack_value=ack_last-1;4:ack_value=ack_last;5:ack_value=ack_last+1;
       6:ack_value=ack_case*32'd2654435761;7:ack_value=~ack_first;
     endcase
     ack_delta=ack_value-ack_first;ack_span=ack_last-ack_first;
     if(dut.in_modular_interval(ack_value,ack_first,ack_last)!==(ack_delta<=ack_span))
       $fatal(1,"Circular ACK interval mismatch %0d",ack_case);
   end
   $display("ACK_INTERVAL_PASS cases=65536 wrap_future_consumer_boundaries");
   repeat(20)@(negedge clk);resetn=1;
   rd('h000,value,0);if(value!==32'h49514131)$fatal(1,"magic");
   rd('h004,value,0);if(value!==iq_build_config::HARDWARE_VERSION)$fatal(1,"version");
   rd('h08c,value,0);if(value!==iq_build_config::CAPABILITIES)$fatal(1,"DMA streaming capability");
   rd('h018,value,0);if(value!=N)$fatal(1,"FFT length");
   rd('h1ec,value,0);if(value!=iq_build_config::FREQUENCY_RECORDS)$fatal(1,"frequency ring capacity");
   rd('h084,value,0);if(value!==0)$fatal(1,"default detector mode");
   rd('h088,value,0);if(value!==32)$fatal(1,"default gap");
   wr('h08c,0,15,0,2); // Capability register is read-only.
   wr('h084,2,15,0,0);wr('h070,1,15,0,2); // Reserved detector mode.
   wr('h084,1,15,0,0);wr('h088,0,15,0,0);wr('h070,1,15,0,2);
   wr('h088,65536,15,0,0);wr('h070,1,15,0,2); // Must not truncate to 16 bits.
   wr('h088,32,15,0,0);wr('h04c,1,15,0,0);wr('h070,1,15,0,0);
   wr('h084,0,15,0,0);wr('h070,1,15,0,2); // Legacy max still >= Kon.
   wr('h04c,1048576,15,0,0);wr('h070,1,15,0,0);
   wr('h10000,32'h11223344,15,3,0);wr('h10000,32'haabbccdd,5,-4,0);
   rd('h10000,value,0);if(value!==32'h11bb33dd)$fatal(1,"WSTRB %h",value);
   wr('h01c,0,0,0,0);rd('h01c,value,0);if(value!=32768)$fatal(1,"zero WSTRB changed config");
   wr('h01c,N,15,0,0);wr('h028,0,15,-2,0);wr('h070,1,15,2,0);
   // Bulk simulation fixture; preceding transactions validate the same RAM host port.
   for(n=0;n<N;n=n+1)case(n%4)
     0:dut.bank0.mem[n]=32'h00002000;1:dut.bank0.mem[n]=32'h20000000;
     2:dut.bank0.mem[n]=32'h0000e000;3:dut.bank0.mem[n]=32'he0000000;
   endcase
   wr('h00c,1,15,0,0);
   wait(dut.run_state==3);
   wr('h078,1,15,0,0);
   wr('h10000,0,15,0,2); // Immutable replay while running.
   wr('h028,1,15,0,2);   // Immutable configuration while running.
   wr('h084,1,15,0,2);wr('h088,1,15,0,2); // New mode/gap are also immutable.
   wait(dut.run_state==0);
   wr('h100,1,15,0,0);
   rd('h134,value,0);while(value!=1)rd('h134,value,0);
   rd('h090,value,0);if(value!==iq_build_config::BUILD_ID[31:0])$fatal(1,"build identity");
   rd('h0a0,value,0);if(value!=iq_build_config::TIMESTAMP_CLOCK_HZ)$fatal(1,"timestamp clock");
   rd('h0a4,value,0);if(value!=1)$fatal(1,"record format");
   rd('h140,value,0);if(value!=N)$fatal(1,"issued snapshot");
   rd('h148,value,0);if(value!=N)$fatal(1,"accepted snapshot");
   rd('h150,value,0);if(value!=0)$fatal(1,"input rejection");
   rd('h154,value,0);if(value==0||value>=4096)$fatal(1,"FIFO high water");
   rd('h160,value,0);if(value!=N)$fatal(1,"FFT accepted samples");
   rd('h168,value,0);if(value!=N)$fatal(1,"FFT output samples");
   rd('h170,value,0);if(value!=1)$fatal(1,"FFT output windows");
   rd('h174,value,0);if(value!=0)$fatal(1,"result queue rejection");
   rd('h178,value,0);if(value!=0)$fatal(1,"input underread");
   rd('h050,producer,0);if(producer!=1)$fatal(1,"producer %d",producer);
   for(j=0;j<32;j=j+1)rd('h30000+j*4,records[j],0);
   if(records[0]!=32'h46525131||records[14]!=TONE_HZ||records[17]!=0||records[21]!=32'h20000000||records[22]!=32'h20000000)$fatal(1,"replay result");
   rd('h07c,value,0);if(value!=1)$fatal(1,"snapshot not ready");
   rd('h3a000+768*8,value,0);if(value!=0)$fatal(1,"snapshot low power");
   rd('h3a000+768*8+4,value,0);if(value!=256)$fatal(1,"snapshot peak %d",value);
   wr('h054,2,15,0,2);wr('h054,1,15,0,0);
   rd('h058,value,0);if(value!=1)$fatal(1,"truncated tone burst count");
   wr('h05c,1,15,0,0);
   wr('h064,32'hffffffff,15,0,0);rd('h060,value,0);if(value!=0)$fatal(1,"errors %h",value);
   // Repeat with Hann after changing configuration: validates config CDC and restart.
   wr('h028,1,15,0,0);wr('h070,1,15,0,0);wr('h078,2,15,0,0);
   wr('h00c,1,15,0,0);wait(dut.run_state==3);wait(dut.run_state==0);
   rd('h050,producer,0);if(producer!=1)$fatal(1,"Hann producer");
   rd('h30000+14*4,value,0);if(value!=TONE_HZ)$fatal(1,"Hann peak");
   rd('h30000+17*4,value,0);if(value!=HANN_TONE_WIDTH_HZ)$fatal(1,"Hann bandwidth %d",value);
   rd('h060,value,0);if(value!=0)$fatal(1,"Hann errors %h",value);
   wr('h054,1,15,0,0);wr('h05c,1,15,0,0);
   // End-to-end digital support: exact 64 samples, crossing the power pipeline.
   wr('h084,1,15,0,0);wr('h088,32,15,0,0);wr('h070,1,15,0,0);
   for(n=0;n<N;n=n+1)dut.bank0.mem[n]=(n>=40&&n<104)?32'h00002000:0;
   wr('h00c,1,15,0,0);wait(dut.run_state==3);wait(dut.run_state==0);
   rd('h058,value,0);if(value!=1)$fatal(1,"digital-zero burst count");
   rd('h38000+1*4,value,0);if(value!=32'h1000)$fatal(1,"digital-zero flags %h",value);
   rd('h38000+6*4,value,0);if(value!=40)$fatal(1,"digital-zero start");
   rd('h38000+8*4,value,0);if(value!=104)$fatal(1,"digital-zero end");
   rd('h38000+10*4,value,0);if(value!=64)$fatal(1,"digital-zero length");
   rd('h38000+11*4,value,0);if(value!=32'h20000000)$fatal(1,"digital-zero peak");
   rd('h38000+12*4,value,0);if(value!=32'h20000000)$fatal(1,"digital-zero RMS");
   rd('h060,value,0);if(value!=0)$fatal(1,"digital-zero errors %h",value);
   // Abort must return to STOPPED without silently starting another replay.
   wr('h00c,4,15,0,0);repeat(100)@(negedge clk);rd('h008,value,0);
   if(value[2:0]!=0)$fatal(1,"abort restarted acquisition");
   // Phase 8: reject malformed AXI Stream framing before accepting a full DMA block.
   wr('h064,32'hffffffff,15,0,0);wr('h184,16,15,0,0);
   wr('h024,1,15,0,0);wr('h070,1,15,0,0);
   wr('h180,0,15,0,0);wr('h18c,N,15,0,0);wr('h194,11,15,0,0);wr('h19c,32'h11111111,15,0,0);wr('h184,3,15,0,0);
   wr('h00c,1,15,0,0);wait(dut.run_state==3);repeat(64)@(negedge clk);
   wr('h1c4,1,15,0,0);wr('h1c8,N,15,0,0);wr('h1cc,21,15,0,0);wr('h1d0,0,15,0,0);wr('h1c0,5,15,0,0);
   axis_send(32'h12345678,1);wait(!dut.loader_active);
   rd('h1d4,value,0);if(!value[2]||value[1])$fatal(1,"early TLAST accepted %h",value);
   rd('h1e4,value,0);if(!(value&1))$fatal(1,"length error missing %h",value);
   // A too-long packet must neither wrap nor overwrite the first word beyond
   // the declared block. The registered guard is tested at the exact boundary.
   wr('h180,1,15,0,0);wr(18'h10000+4*N,32'hcafef00d,15,0,0);
   wr('h1c0,5,15,0,0);
   for(n=0;n<N;n=n+1)axis_send(32'h12345678,0);
   axis_send(32'hdeadbeef,1);wait(!dut.loader_active);
   rd('h1e4,value,0);if((value&32'hc)!=32'hc)$fatal(1,"overlong block errors missing %h",value);
   rd('h1d8,value,0);if(value!=N+1)$fatal(1,"overlong received count %d",value);
   if(dut.bank1.mem[N]!==32'hcafef00d)$fatal(1,"overlong DMA wrote outside declared block");
   rd('h1d4,value,0);if(value[1]||!value[2])$fatal(1,"overlong block became ready");
   // Loader ownership rejects host metadata/ready/clear mutations, including
   // status clear while busy; explicit abort releases ownership without ready.
   wr('h1c0,5,15,0,0);axis_send(32'h12345678,0);
   wr('h190,N,15,0,2);wr('h184,1,15,0,2);wr('h184,8,15,0,2);
   wr('h1c0,4,15,0,2);
   if(!dut.loader_active||dut.bank_ready[1])$fatal(1,"host changed loader ownership");
   wr('h1c0,2,15,0,0);
   if(dut.loader_active||dut.bank_ready[1])$fatal(1,"abort did not release incomplete bank");
   rd('h1e4,value,0);if(!(value&32'h20))$fatal(1,"abort flag missing");
   wr('h184,16,15,0,0);
   // Load the inactive bank through the DMA-facing stream while analysis continues.
   dma_crc=32'hffffffff;for(n=0;n<N;n=n+1)dma_crc=crc_word(dma_crc,32'h12345678);dma_crc=dma_crc^32'hffffffff;
   wr('h1c8,N,15,0,0);wr('h1cc,22,15,0,0);wr('h1d0,dma_crc,15,0,0);wr('h1c0,5,15,0,0);
   for(n=0;n<N;n=n+1)axis_send(32'h12345678,n==(N-1));
   wait(!dut.loader_active);
   rd('h1d4,value,0);if(!value[1]||value[2]||value[0])$fatal(1,"DMA load failed %h",value);
   rd('h1d8,value,0);if(value!=N)$fatal(1,"DMA received count %d",value);
   rd('h1dc,value,0);if(value!=dma_crc)$fatal(1,"DMA CRC %h != %h",value,dma_crc);
   rd('h1e0,value,0);if(value!=1)$fatal(1,"DMA transfer count");
   if(dut.bank1.mem[0]!==32'h12345678||dut.bank1.mem[(N-1)]!==32'h12345678)$fatal(1,"DMA bank contents");
   wr('h180,0,15,0,0);wr('h10000,0,15,0,2);
   wr('h180,1,15,0,0);wr('h184,2,15,0,0);
   rd('h188,value,0);if(value[0]!=0||!value[3])$fatal(1,"stream armed status %h",value);
   wr('h10000,32'hdeadbeef,15,0,2); // Pending bank is immutable until the boundary switch.
   while(dut.issued[LOGN-1:0]!=(N-2))@(negedge clk);
   if(dut.active_bank!=0)$fatal(1,"stream switched before FFT boundary");
   repeat(4)@(negedge clk);rd('h188,value,0);if(value[0]!=1||value[3])$fatal(1,"stream did not switch %h",value);
   rd('h1a4,value,0);if(value!=1)$fatal(1,"switch count");rd('h1a8,value,0);if(value!=22)$fatal(1,"block id");
   rd('h1b4,value,0);if(value!=2)$fatal(1,"write reject count");
   wr('h180,0,15,0,0);wr('h10000,32'h87654321,15,0,0);
   wr('h00c,2,15,0,0);wait(dut.run_state==0);
   if(replay_checked<2*N||replay_switches<1)$fatal(1,"Insufficient replay alignment coverage");
   $display("REPLAY_PIPELINE_SCOREBOARD_PASS samples=%0d switches=%0d",replay_checked,replay_switches);
   $display("AXI_PASS independent_aw_w wstrb response_stalls ddr_dma_crc_tlast overlong_dma_write_guard dual_bank_boundary_switch block_identity rect_hann_restart snapshot consumer_bounds abort digital_zero_config exact_frame");$finish;
 end
 initial begin #4000000;$fatal(1,"AXI timeout");end
endmodule
