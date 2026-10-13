`timescale 1ns/1ps
module record_ring #(parameter WORDS_LOG2=5,RECORDS_LOG2=8)(
 input wire clk,rst,input wire push,input wire [(32<<WORDS_LOG2)-1:0] record_data,
 input wire [31:0] consumer,output reg [31:0] producer,dropped,output reg busy,output wire has_space,
 input wire [WORDS_LOG2+RECORDS_LOG2-1:0] read_addr,output reg [31:0] read_data);
 localparam AW=WORDS_LOG2+RECORDS_LOG2;
 (* ram_style="block" *) reg [31:0] mem[0:(1<<AW)-1];
 reg [(32<<WORDS_LOG2)-1:0] staging;
 reg [WORDS_LOG2-1:0] word_index;
 wire [AW-1:0] write_addr={producer[RECORDS_LOG2-1:0],word_index};
 // Exact modulo-2^32 capacity comparison. Split the low-page borrow from
 // the upper-page equality instead of a full-width subtract followed by a
 // wide threshold comparison on the busy/drop control path.
 // Check the page increment in parallel five-bit chunks. Each chunk's
 // carry is the AND of all lower consumer page bits, avoiding a long page
 // increment followed by a wide equality test. Preserve modulo-2^32 wrap.
 localparam PAGE_BITS=32-RECORDS_LOG2,PAGE_CHUNKS=(PAGE_BITS+4)/5;
 wire [PAGE_CHUNKS-1:0] next_page_match;
 genvar page_chunk;
 generate for(page_chunk=0;page_chunk<PAGE_CHUNKS;page_chunk=page_chunk+1)begin:page_lookahead
   localparam OFFSET=page_chunk*5;
   localparam WIDTH=(PAGE_BITS-OFFSET<5)?PAGE_BITS-OFFSET:5;
   wire carry_in;
   if(page_chunk==0)assign carry_in=1'b1;
   else assign carry_in=&consumer[RECORDS_LOG2+:OFFSET];
   wire [WIDTH-1:0] next_chunk=consumer[RECORDS_LOG2+OFFSET+:WIDTH]+carry_in;
   assign next_page_match[page_chunk]=producer[RECORDS_LOG2+OFFSET+:WIDTH]==next_chunk;
 end endgenerate
 assign has_space=producer[RECORDS_LOG2-1:0]>=consumer[RECORDS_LOG2-1:0]?
   producer[31:RECORDS_LOG2]==consumer[31:RECORDS_LOG2]:(&next_page_match);

 always @(posedge clk) begin
   read_data<=mem[read_addr];
   if(busy&&!rst)mem[write_addr]<=staging[31:0];
 end
 always @(posedge clk)begin
   if(rst)begin producer<=0;dropped<=0;busy<=0;word_index<=0;staging<=0;end
   else begin
     // Keep the 1024/512-bit staging mux dependent only on registered busy and
     // push. Capacity arithmetic controls ownership, not every staging bit.
     if(busy)staging<=staging>>32;
     else if(push)staging<=record_data;
     else staging<=0;
     if(push)begin
       if(busy||!has_space)dropped<=dropped+1;
       else begin word_index<=0;busy<=1;end
     end
     if(busy)begin
       word_index<=word_index+1;
       if(&word_index)begin busy<=0;producer<=producer+1;end
     end
   end
 end
endmodule
