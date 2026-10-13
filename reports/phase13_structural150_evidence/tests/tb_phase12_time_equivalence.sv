`timescale 1ns/1ps
module tb_phase12_time_equivalence;
 reg clk=0;always #3.333 clk=~clk;
 reg rst=1,valid=0,finish=0;
 reg [31:0] iq=0,max_burst=1048576;
 reg [15:0] kon=1,koff=1;
 reg [63:0] tick=0;
 always @(posedge clk)tick<=tick+1;
 wire wv,bv,rwv,rbv;
 wire [191:0] wd,rwd;
 wire [287:0] bd,rbd;
 wire [63:0] samples,rsamples;
 time_measure dut(.clk(clk),.rst(rst),.valid(valid),.iq(iq),.tick(tick),.finish(finish),
  .ton(36'd1048576),.toff(36'd262144),.kon(kon),.koff(koff),.max_burst(max_burst),
  .detector_mode(1'b0),.gap_min(16'd32),.window_valid(wv),.window_data(wd),
  .burst_valid(bv),.burst_data(bd),.samples(samples));
 phase11_time_measure baseline(.clk(clk),.rst(rst),.valid(valid),.iq(iq),.tick(tick),.finish(finish),
  .ton(36'd1048576),.toff(36'd262144),.kon(kon),.koff(koff),.max_burst(max_burst),
  .detector_mode(1'b0),.gap_min(16'd32),.window_valid(rwv),.window_data(rwd),
  .burst_valid(rbv),.burst_data(rbd),.samples(rsamples));
 integer comparisons=0,bursts=0,windows=0,c,n,count;
 always @(negedge clk)if(!rst)begin
  comparisons=comparisons+1;
  if({wv,bv,samples}!=={rwv,rbv,rsamples})$fatal(1,"Time control mismatch case=%0d",c);
  if(wv)begin windows=windows+1;if(wd!==rwd)$fatal(1,"Window mismatch");end
  if(bv)begin bursts=bursts+1;if(bd!==rbd)$fatal(1,"Burst mismatch case=%0d",c);end
 end
 task drive(input integer length,input [31:0] value);
  integer k;
  begin
   for(k=0;k<length;k=k+1)begin
    @(negedge clk);valid=1;iq=value;
    if(k%127==126)begin @(negedge clk);valid=0;repeat(3)@(negedge clk);end
   end
  end
 endtask
 initial begin
  for(c=0;c<10;c=c+1)begin
   @(posedge clk);#1;rst=1;valid=0;finish=0;
   case(c%5)
    0:begin kon=1;koff=1;end
    1:begin kon=2;koff=2;end
    2:begin kon=8;koff=32;end
    3:begin kon=255;koff=65535;end
    4:begin kon=65535;koff=255;end
   endcase
   max_burst=(c%3==0)?{16'd0,kon}:32'd1048576;
   // Match the peripheral contract: configuration settles while reset/stopped.
   repeat(8)@(posedge clk);#1;rst=0;
   drive(20,0);
   if(c<5)begin drive(kon+100,32'd8192);drive(koff+32,0);end
   else begin
    drive(kon>1?kon-1:1,32'd8192);drive(100,0);
    drive(kon+80,32'd8192);drive(16,0);drive(80,32'd8192);
   end
   @(negedge clk);valid=0;finish=1;
   @(negedge clk);finish=0;repeat(30)@(posedge clk);
  end
  if(bursts==0||windows==0)$fatal(1,"Empty equivalence coverage");
  $display("PHASE12_TIME_EQUIVALENCE_PASS cycles=%0d bursts=%0d windows=%0d kon_koff_1_2_8_32_255_65535 bubbles_timeout_finish",comparisons,bursts,windows);
  $finish;
 end
 initial begin #10000000;$fatal(1,"Time equivalence timeout");end
endmodule
