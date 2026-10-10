`timescale 1ns/1ps
// Restoring integer square root: exact floor(sqrt(rad)), 32 clocks.
module isqrt64(input wire clk, rst, start, input wire [63:0] rad,
 output reg busy, done, output reg [31:0] root);
 reg [63:0] bits_left;
 reg [65:0] remnant;
 reg [5:0] steps;
 wire [65:0] trial_rem = (remnant << 2) | {64'b0,bits_left[63:62]};
 wire [65:0] trial_sub = ({34'b0,root} << 2) | 66'd1;
 always @(posedge clk) begin
   done <= 0;
   if (rst) begin busy<=0; root<=0; remnant<=0; bits_left<=0; steps<=0; end
   else if (start && !busy) begin busy<=1; root<=0; remnant<=0; bits_left<=rad; steps<=0; end
   else if (busy) begin
     bits_left<=bits_left<<2;
     if (trial_rem>=trial_sub) begin remnant<=trial_rem-trial_sub; root<=(root<<1)|1; end
     else begin remnant<=trial_rem; root<=root<<1; end
     steps<=steps+1;
     if(steps==31) begin busy<=0; done<=1; end
   end
 end
endmodule

// Unsigned 64/64 divider. Denominator zero is reported; no combinational '/'.
module udiv64(input wire clk,rst,start,input wire [63:0] numerator,denominator,
 output reg busy,done,divide_by_zero,output reg [63:0] quotient,remainder);
 reg [63:0] dividend, divisor;
 reg [5:0] count;
 wire [64:0] rnext={remainder,dividend[63]};
 always @(posedge clk) begin
   done<=0;
   if(rst) begin busy<=0;divide_by_zero<=0;quotient<=0;remainder<=0;dividend<=0;divisor<=0;count<=0; end
   else if(start && !busy) begin
     quotient<=0;remainder<=0;dividend<=numerator;divisor<=denominator;count<=0;
     divide_by_zero<=denominator==0;
     if(denominator==0) begin done<=1;busy<=0;end else busy<=1;
   end else if(busy) begin
     dividend<=dividend<<1;
     if(rnext>={1'b0,divisor}) begin remainder<=rnext-divisor;quotient<=(quotient<<1)|1;end
     else begin remainder<=rnext[63:0];quotient<=quotient<<1;end
     count<=count+1;
     if(count==63) begin busy<=0;done<=1;end
   end
 end
endmodule
