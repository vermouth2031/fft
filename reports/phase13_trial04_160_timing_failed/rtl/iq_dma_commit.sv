`timescale 1ns/1ps
// Terminal block validation is deliberately separate from the CRC recurrence.
// Inputs are captured once; the loader retains ownership until finish is consumed.
module iq_dma_commit(
 input wire clk,rst,cancel,start,
 input wire target,
 input wire [31:0] length,block_id,expected_crc,computed_crc,errors,
 output reg finish,commit0,commit1,
 output reg target_q,
 output reg [31:0] length_q,block_q,crc_q,error_q,
 output wire busy);
 localparam IDLE=0,CHECK=1,ROUTE=2,COMPLETE=3;
 reg [1:0] state;
 reg [31:0] expected_q;
 reg failed;
 assign busy=state!=IDLE;
 always @(posedge clk)begin
   finish<=0;commit0<=0;commit1<=0;
   if(rst||cancel)begin
     state<=IDLE;failed<=0;target_q<=0;length_q<=0;block_q<=0;
     expected_q<=0;crc_q<=0;error_q<=0;
   end else case(state)
     IDLE:if(start)begin
       target_q<=target;length_q<=length;block_q<=block_id;
       expected_q<=expected_crc;crc_q<=computed_crc;error_q<=errors;
       state<=CHECK;
     end
     CHECK:begin
       failed<=(error_q!=0)||(crc_q!=expected_q);
       if(crc_q!=expected_q)error_q<=error_q|32'h10;
       state<=ROUTE;
     end
     ROUTE:begin
       commit0<=!failed&&!target_q;commit1<=!failed&&target_q;
       finish<=1;state<=COMPLETE;
     end
     COMPLETE:state<=IDLE;
     default:state<=IDLE;
   endcase
 end
endmodule
