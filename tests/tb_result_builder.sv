`timescale 1ns/1ps
module tb_result_builder;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,empty=1;reg [63:0] tick=0;always @(posedge clk)tick<=tick+1;
 reg [191:0] ctx=0;reg [255:0] freq=0;
 wire pop,fv;wire [1023:0] rec;
 result_builder dut(.clk(clk),.rst(rst),.tick(tick),.epoch(32'd1),.config_id(32'd1),.hann(1'b0),.integrity_flags(32'd0),
 .ctx(ctx),.ctx_empty(empty),.ctx_pop(),.freq(freq),.freq_empty(empty),.freq_pop(pop),
 .burst(288'd0),.burst_empty(1'b1),.burst_pop(),.freq_valid(fv),.freq_record(rec),.burst_valid(),.burst_record(),
 .completed(),.max_latency(),.metadata_error());
 integer k,lo,hi;reg signed [63:0] p,l,h,c,b;
 function automatic [31:0] nearest(input signed [63:0] num,input integer denom);
   begin nearest=num<0?-((-num+denom/2)/denom):(num+denom/2)/denom;end
 endfunction
 initial begin
   repeat(5)@(negedge clk);rst=0;
   for(k=0;k<8192;k=k+1)begin
     lo=k/2;hi=4096+k/2;
     @(negedge clk);ctx={32'd0,tick,64'd549755813888,32'd67108864};
     freq={32'd0,32'd0,64'd1,48'd1,16'(k),16'(lo),16'(hi),32'd0};empty=0;
     wait(pop);@(negedge clk);empty=1;wait(fv);@(negedge clk);
     p=(k-4096)*64'sd100000000;l=(lo-4096)*64'sd100000000;h=(hi-4096)*64'sd100000000;
     c=(lo+hi-8192)*64'sd100000000;b=(hi-lo)*64'sd100000000;
     if(rec[14*32+:32]!==nearest(p,8192)||rec[15*32+:32]!==nearest(l,8192)||
        rec[16*32+:32]!==nearest(h,8192)||rec[17*32+:32]!==nearest(b,8192)||rec[18*32+:32]!==nearest(c,16384))$fatal(1,"frequency rounding bin %d",k);
     if(rec[21*32+:32]!=32'h20000000||rec[22*32+:32]!=32'h20000000)$fatal(1,"amplitude packing");
   end
   $display("BUILDER_PASS all_8192_bins signed_rounding bandcenter width amplitude");$finish;
 end
 initial begin #10000000;$fatal(1,"builder timeout");end
endmodule
