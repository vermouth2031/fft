`timescale 1ns/1ps
// Mutually exclusive read/write operations allow one distributed-RAM address
// port, avoiding a duplicated LUTRAM read port. No reset of memory contents.
module spectrum_lane #(parameter integer AW=10,parameter STYLE="block")(
 input wire clk,we,re,input wire [AW-1:0] write_addr,read_addr,
 input wire [47:0] data,output reg [47:0] q);
 (* ram_style=STYLE *) reg [47:0] memory[0:(1<<AW)-1];
 wire [AW-1:0] address=we?write_addr:read_addr;
 always @(posedge clk)begin
   if(we)memory[address]<=data;
   if(re)q<=memory[address];
 end
endmodule
