`timescale 1ns/1ps
// One true dual-port replay bank: AXI host read/write on A, sample replay on B.
module iq_replay_bank(
 input wire clk,
 input wire [14:0] host_addr,
 input wire host_en,host_we,
 input wire [3:0] host_wstrb,
 input wire [31:0] host_wdata,
 output reg [31:0] host_q,
 input wire replay_en,
 input wire [14:0] replay_addr,
 output reg [31:0] replay_q);
 (* ram_style="block" *) reg [31:0] mem[0:32767];
 integer byte_lane;
 always @(posedge clk)begin
   // Use the BRAM's native port enables. Inactive banks and idle host
   // ports retain their output, avoiding continuous unused RAM accesses.
   if(host_en)begin
     host_q<=mem[host_addr];
     if(host_we)for(byte_lane=0;byte_lane<4;byte_lane=byte_lane+1)
       if(host_wstrb[byte_lane])mem[host_addr][byte_lane*8+:8]<=host_wdata[byte_lane*8+:8];
   end
   if(replay_en)replay_q<=mem[replay_addr];
 end
endmodule
