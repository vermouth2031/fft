`timescale 1ns/1ps
module tb_burst_edges;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,valid=0,finish=0;reg [31:0] iq=0,maximum=8;reg [15:0] kon=8,koff=1;
 wire bv;wire [287:0] bd;integer n,c=0,count=0;
 time_measure dut(.clk(clk),.rst(rst),.valid(valid),.iq(iq),.tick(64'd0),.finish(finish),
 .ton(36'd1048576),.toff(36'd262144),.kon(kon),.koff(koff),.max_burst(maximum),.detector_mode(1'b0),.gap_min(16'd32),
 .window_valid(),.window_data(),.burst_valid(bv),.burst_data(bd),.samples());
 always @(posedge clk)if(!rst&&bv)begin
   if(c<2)begin
     if(bd[287:256]!=1024||bd[223:160]!=count*maximum||bd[159:96]!=(count+1)*maximum||
       bd[95:32]!=64'd67108864*maximum||bd[31:0]!=67108864)$fatal(1,"timeout boundary case=%0d count=%0d data=%h",c,count,bd);
   end else if(bd[287:256]!=0||bd[223:160]!=0||bd[159:96]!=47||bd[95:32]!=64'd2147483648)
     $fatal(1,"single-confirmation tail boundary %h",bd);
   count=count+1;
 end
 initial begin
   for(c=0;c<3;c=c+1)begin
     @(negedge clk);rst=1;valid=0;finish=0;count=0;
     kon=c==0?8:1;maximum=c==0?8:(c==1?1:1048576);
     repeat(10)@(negedge clk);rst=0;
     for(n=0;n<(c==2?64:32);n=n+1)begin
       @(negedge clk);valid=1;iq=n<32?32'd8192:0;
     end
     @(negedge clk);valid=0;finish=1;
     @(negedge clk);finish=0;repeat(20)@(negedge clk);
     if(count!=(c==0?4:(c==1?32:1)))$fatal(1,"event count %0d",c);
   end
   $display("BURST_EDGES_PASS Kon1_Koff1 max1 max_equals_Kon delayed_finish");$finish;
 end
 initial begin #200000;$fatal(1,"timeout");end
endmodule
