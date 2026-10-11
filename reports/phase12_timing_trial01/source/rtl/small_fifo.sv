`timescale 1ns/1ps
// Small distributed FIFO. A full queue never overwrites unread data.
module small_fifo #(parameter W=32, AW=4)(input wire clk,rst,
 input wire push,input wire [W-1:0] din,output wire full,
 input wire pop,output wire [W-1:0] dout,output wire empty);
 (* ram_style="distributed" *) reg [W-1:0] mem[0:(1<<AW)-1];
 reg [AW-1:0] wp,rp;
 reg [AW:0] used;
 assign full=used==(1<<AW);assign empty=used==0;assign dout=mem[rp];
 wire wr=push&&!full, rd=pop&&!empty;
 always @(posedge clk) begin
   if(rst) begin wp<=0;rp<=0;used<=0;end
   else begin
     if(wr) begin mem[wp]<=din;wp<=wp+1;end
     if(rd) rp<=rp+1;
     case({wr,rd}) 2'b10:used<=used+1;2'b01:used<=used-1;default:used<=used;endcase
   end
 end
endmodule
