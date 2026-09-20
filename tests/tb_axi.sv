`timescale 1ns/1ps
module tb_axi;
 reg clk=0,fft_clk=0;always #5 clk=~clk;always #4 fft_clk=~fft_clk;
 reg resetn=0;reg [17:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
 reg [31:0] wdata=0;reg [3:0] wstrb=15;
 wire awready,wready,bvalid,arready,rvalid;wire [1:0] bresp,rresp;wire [31:0] rdata;
 iq_peripheral dut(.s_axi_aclk(clk),.s_axi_aresetn(resetn),.fft_clk(fft_clk),
 .s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
 .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
 .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
 .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
 .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready));
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
 integer n,j;reg [31:0] value,producer;reg [31:0] records[0:31];
 initial begin
   repeat(20)@(negedge clk);resetn=1;
   rd('h000,value,0);if(value!==32'h49514131)$fatal(1,"magic");
   rd('h004,value,0);if(value!==32'h00010001)$fatal(1,"version");
   rd('h08c,value,0);if(value!==1)$fatal(1,"digital-zero capability");
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
   wr('h01c,8192,15,0,0);wr('h028,0,15,-2,0);wr('h070,1,15,2,0);
   // Bulk simulation fixture; preceding transactions validate the same RAM host port.
   for(n=0;n<8192;n=n+1)case(n%4)
     0:dut.replay_mem[n]=32'h00002000;1:dut.replay_mem[n]=32'h20000000;
     2:dut.replay_mem[n]=32'h0000e000;3:dut.replay_mem[n]=32'he0000000;
   endcase
   wr('h00c,1,15,0,0);
   wait(dut.run_state==3);
   wr('h078,1,15,0,0);
   wr('h10000,0,15,0,2); // Immutable replay while running.
   wr('h028,1,15,0,2);   // Immutable configuration while running.
   wr('h084,1,15,0,2);wr('h088,1,15,0,2); // New mode/gap are also immutable.
   wait(dut.run_state==0);
   rd('h050,producer,0);if(producer!=1)$fatal(1,"producer %d",producer);
   for(j=0;j<32;j=j+1)rd('h30000+j*4,records[j],0);
   if(records[0]!=32'h46525131||records[14]!=25000000||records[17]!=0||records[21]!=32'h20000000||records[22]!=32'h20000000)$fatal(1,"replay result");
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
   rd('h30000+14*4,value,0);if(value!=25000000)$fatal(1,"Hann peak");
   rd('h30000+17*4,value,0);if(value!=24414)$fatal(1,"Hann bandwidth %d",value);
   rd('h060,value,0);if(value!=0)$fatal(1,"Hann errors %h",value);
   wr('h054,1,15,0,0);wr('h05c,1,15,0,0);
   // End-to-end digital support: exact 64 samples, crossing the power pipeline.
   wr('h084,1,15,0,0);wr('h088,32,15,0,0);wr('h070,1,15,0,0);
   for(n=0;n<8192;n=n+1)dut.replay_mem[n]=(n>=40&&n<104)?32'h00002000:0;
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
   $display("AXI_PASS independent_aw_w wstrb response_stalls replay_lock rect_hann_restart snapshot consumer_bounds abort digital_zero_config exact_frame");$finish;
 end
 initial begin #1000000;$fatal(1,"AXI timeout");end
endmodule
