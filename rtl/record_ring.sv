`timescale 1ns/1ps
module record_ring #(parameter WORDS_LOG2=5,RECORDS_LOG2=8)(
 input wire clk,rst,input wire push,input wire [(32<<WORDS_LOG2)-1:0] record_data,
 input wire [31:0] consumer,output reg [31:0] producer,dropped,output reg busy,
 input wire [WORDS_LOG2+RECORDS_LOG2-1:0] read_addr,output reg [31:0] read_data);
 localparam AW=WORDS_LOG2+RECORDS_LOG2;
 (* ram_style="block" *) reg [31:0] mem[0:(1<<AW)-1];
 reg [(32<<WORDS_LOG2)-1:0] staging;
 reg [WORDS_LOG2-1:0] word_index;
 wire [AW-1:0] write_addr={producer[RECORDS_LOG2-1:0],word_index};
 always @(posedge clk) begin
   read_data<=mem[read_addr];
   if(busy&&!rst)mem[write_addr]<=staging[31:0];
 end
 always @(posedge clk)begin
   if(rst)begin producer<=0;dropped<=0;busy<=0;word_index<=0;staging<=0;end
   else begin
     if(push)begin
       if(busy||(producer-consumer)>=(1<<RECORDS_LOG2))dropped<=dropped+1;
       else begin staging<=record_data;word_index<=0;busy<=1;end
     end
     if(busy)begin
       staging<=staging>>32;word_index<=word_index+1;
       if(&word_index)begin busy<=0;producer<=producer+1;end
     end
   end
 end
endmodule
