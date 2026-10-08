`timescale 1ns/1ps
// Mutually exclusive read/write operations allow one distributed-RAM address
// port, avoiding a duplicated LUTRAM read port. Register the selected address
// before RAM access so bank/lane decoding is not on the deep LUTRAM read path.
// Read latency is two clocks. Memory contents are intentionally not reset.
module spectrum_lane #(parameter integer AW=10,parameter STYLE="block")(
 input wire clk,we,re,input wire [AW-1:0] write_addr,read_addr,
 input wire [47:0] data,output reg [47:0] q);
 (* ram_style=STYLE *) reg [47:0] memory[0:(1<<AW)-1];
 reg [AW-1:0] address;
 reg write_enable,read_enable;
 reg [47:0] write_data;
 always @(posedge clk)begin
   address<=we?write_addr:read_addr;
   write_enable<=we;read_enable<=re;write_data<=data;
   if(write_enable)memory[address]<=write_data;
   if(read_enable)q<=memory[address];
 end
endmodule
