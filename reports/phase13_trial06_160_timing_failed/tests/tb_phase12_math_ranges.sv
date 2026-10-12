`timescale 1ns/1ps
module tb_phase12_math_ranges;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,start=0;reg [63:0] num=0,den=1;
 wire sb,sd,db,dd,dz;wire [31:0] root;wire [63:0] q,r;
 isqrt64 sq(.clk(clk),.rst(rst),.start(start),.rad(num),.busy(sb),.done(sd),.root(root));
 udiv64 dv(.clk(clk),.rst(rst),.start(start),.numerator(num),.denominator(den),
  .busy(db),.done(dd),.divide_by_zero(dz),.quotient(q),.remainder(r));
 reg [287:0] golden[0:10219];
 integer n,k,roots,divisions;
 initial begin
  $readmemh("phase12_math_ranges.mem",golden);
  repeat(4)@(negedge clk);rst=0;
  num=64'hffffffffffffffff;den=200;start=1;
  @(negedge clk);start=0;repeat(10)@(negedge clk);rst=1;
  @(negedge clk);
  if(sb||sd||db||dd||root!=0||q!=0||r!=0)$fatal(1,"Mid-operation reset failed");
  rst=0;
  for(n=0;n<10220;n=n+1)begin
   @(negedge clk);num=golden[n][287:224];den=golden[n][223:160];start=1;
   @(negedge clk);start=0;roots=0;divisions=0;
   for(k=0;k<65;k=k+1)begin
    if(sd)begin
     roots=roots+1;
     if(root!==golden[n][31:0])$fatal(1,"sqrt boundary n=%0d rad=%h",n,num);
    end
    if(dd)begin
     divisions=divisions+1;
     if(q!==golden[n][159:96]||r!==golden[n][95:32]||dz!==(den==0))$fatal(1,"divide boundary n=%0d",n);
    end
    @(negedge clk);
   end
   if(roots!=1||divisions!=1||sb||db)$fatal(1,"Math completion count n=%0d",n);
  end
  $display("PHASE12_MATH_RANGES_PASS vectors=10220 exact_native_integer_reference zero_divisor mid_operation_reset");
  $finish;
 end
 initial begin #12000000;$fatal(1,"Math boundary timeout");end
endmodule
