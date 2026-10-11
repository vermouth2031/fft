`timescale 1ns/1ps
// Restoring integer square root: exact floor(sqrt(rad)), 32 clocks.
module isqrt64(input wire clk, rst, start, input wire [63:0] rad,
 output reg busy, done, output reg [31:0] root);
 reg [63:0] bits_left;
 // For a 64-bit radicand, remainder < 2*root+1 <= 2^33-1.
 // Two appended radicand bits require 35 trial bits, without truncation.
 reg [32:0] remnant;
 reg [5:0] steps;
 wire [34:0] trial_rem = {remnant,bits_left[63:62]};
 wire [34:0] trial_sub = ({3'b0,root} << 2) | 35'd1;
 wire [35:0] root_difference={1'b0,trial_rem}-{1'b0,trial_sub};
 always @(posedge clk) begin
   done <= 0;
   if (rst) begin busy<=0; root<=0; remnant<=0; bits_left<=0; steps<=0; end
   else if (start && !busy) begin busy<=1; root<=0; remnant<=0; bits_left<=rad; steps<=0; end
   else if (busy) begin
     bits_left<=bits_left<<2;
     if (!root_difference[35]) begin remnant<=root_difference[32:0]; root<=(root<<1)|1; end
     else begin remnant<=trial_rem[32:0]; root<=root<<1; end
     steps<=steps+1;
     if(steps==31) begin busy<=0; done<=1; end
   end
 end
endmodule

// Unsigned restoring divider: numerator and quotient remain 64 bits.
// The remainder is always below the divisor; a narrower divisor therefore
// needs only DIVISOR_WIDTH remainder bits, without approximation or truncation.
module udiv64 #(parameter integer DIVISOR_WIDTH=64)(
 input wire clk,rst,start,input wire [63:0] numerator,
 input wire [DIVISOR_WIDTH-1:0] denominator,
 output reg busy,done,divide_by_zero,output reg [63:0] quotient,output wire [63:0] remainder);
 reg [63:0] dividend;
 reg [DIVISOR_WIDTH-1:0] divisor,remnant;
 assign remainder={{(64-DIVISOR_WIDTH){1'b0}},remnant};
 reg [5:0] count;
 wire [DIVISOR_WIDTH:0] rnext={remnant,dividend[63]};
 // A single extended subtraction provides both comparison (borrow) and
 // remainder. Avoid a comparator followed by a second carry chain.
 wire [DIVISOR_WIDTH+1:0] difference={1'b0,rnext}-{2'b0,divisor};
 always @(posedge clk) begin
   done<=0;
   if(rst) begin busy<=0;divide_by_zero<=0;quotient<=0;remnant<=0;dividend<=0;divisor<=0;count<=0; end
   else if(start && !busy) begin
     quotient<=0;remnant<=0;dividend<=numerator;divisor<=denominator;count<=0;
     divide_by_zero<=denominator==0;
     if(denominator==0) begin done<=1;busy<=0;end else busy<=1;
   end else if(busy) begin
     dividend<=dividend<<1;
     if(!difference[DIVISOR_WIDTH+1]) begin remnant<=difference[DIVISOR_WIDTH-1:0];quotient<=(quotient<<1)|1;end
     else begin remnant<=rnext[DIVISOR_WIDTH-1:0];quotient<=quotient<<1;end
     count<=count+1;
     if(count==63) begin busy<=0;done<=1;end
   end
 end
endmodule
