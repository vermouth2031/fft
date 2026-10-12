`timescale 1ns/1ps
// One writer owns each bank's metadata. Commit payload and enable arrive from
// registers, independent of CRC logic and transfer-counter carry chains.
module iq_bank_metadata(
 input wire clk,rst,release_bank,invalidate,host_ready,
 input wire host_length_we,host_block_we,host_crc_we,
 input wire [31:0] host_data,
 input wire [3:0] host_strobe,
 input wire commit,
 input wire [31:0] commit_length,commit_block,commit_crc,
 output reg ready,
 output reg [31:0] length,block_id,crc);
 function automatic [31:0] merge(input [31:0] old_value,new_value,input [3:0] strobe);
   integer b;
   begin for(b=0;b<4;b=b+1)merge[b*8+:8]=strobe[b]?new_value[b*8+:8]:old_value[b*8+:8];end
 endfunction
 always @(posedge clk)begin
   if(rst)begin ready<=0;length<=0;block_id<=0;crc<=0;end
   else begin
     if(commit)begin length<=commit_length;block_id<=commit_block;crc<=commit_crc;end
     else begin
       if(host_length_we)length<=merge(length,host_data,host_strobe);
       if(host_block_we)block_id<=merge(block_id,host_data,host_strobe);
       if(host_crc_we)crc<=merge(crc,host_data,host_strobe);
     end
     if(invalidate||release_bank)ready<=0;
     else if(commit||host_ready)ready<=1;
   end
 end
endmodule
