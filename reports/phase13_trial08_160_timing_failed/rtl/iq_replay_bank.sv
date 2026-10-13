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
 // Keep each byte read/write pair in the same process. This lets synthesis
 // infer the native A-port enable for byte-write BRAM instead of a held
 // fabric output with an always-enabled memory port.
 genvar lane;
 generate for(lane=0;lane<4;lane=lane+1)begin:bytes
   always @(posedge clk)if(host_en)begin
     if(host_we&&host_wstrb[lane])mem[host_addr][lane*8+:8]<=host_wdata[lane*8+:8];
     host_q[lane*8+:8]<=mem[host_addr][lane*8+:8];
   end
 end endgenerate
 always @(posedge clk)if(replay_en)replay_q<=mem[replay_addr];
endmodule
