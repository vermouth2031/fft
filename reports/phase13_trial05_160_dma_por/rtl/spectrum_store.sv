`timescale 1ns/1ps
// One complete spectrum. Port A scans the previous frame, then drains deferred
// writes. Port B accepts the current FFT output after the scan has released RAM.
// Both address paths are registered; scan read latency remains two clocks.
module spectrum_shared_lane #(parameter integer AW=11)(
 input wire clk, input wire re,input wire [AW-1:0] read_addr,
 input wire drain_we,input wire [AW-1:0] drain_addr,input wire [47:0] drain_data,
 input wire live_we,input wire [AW-1:0] live_addr,input wire [47:0] live_data,
 output reg [47:0] q);
 (* ram_style="block" *) reg [47:0] memory[0:(1<<AW)-1];
 reg [AW-1:0] address_a,address_b;
 reg [47:0] data_a,data_b;
 reg read_a,write_a,write_b;
 always @(posedge clk)begin
   address_a<=re?read_addr:drain_addr;data_a<=drain_data;
   read_a<=re;write_a<=drain_we;
   if(write_a)memory[address_a]<=data_a;
   if(read_a)q<=memory[address_a];
 end
 always @(posedge clk)begin
   address_b<=live_addr;data_b<=live_data;write_b<=live_we;
   if(write_b)memory[address_b]<=data_b;
 end
endmodule

// Linear per-frame queue. Only the short scan overlap is buffered; it is fully
// drained before the next frame ends. Banking bounds the distributed RAM mux
// depth and registers the bank selection separately from the RAM read.
module spectrum_deferred_queue #(parameter integer W=62,BANKS=5)(
 input wire clk,rst,protect,input wire push,input wire [W-1:0] din,
 output reg pop_valid,output reg [W-1:0] pop_data,
 output wire pending,output reg overflow);
 localparam integer CAPACITY=BANKS*512,AW=$clog2(CAPACITY+1),BW=$clog2(BANKS);
 reg [AW-1:0] written,requested;
 wire take_write=protect&&push&&!rst;
 wire take_read=!protect&&requested<written&&!rst;
 wire [W-1:0] bank_q[0:BANKS-1];
 reg read_valid;
 reg [BW-1:0] read_bank;
 assign pending=written!=requested||read_valid||pop_valid;
 genvar b;
 generate for(b=0;b<BANKS;b=b+1)begin: banks
   (* ram_style="distributed" *) reg [W-1:0] memory[0:511];
   // Local shadow counters have exactly the global counters' low bits, but
   // drive only this physical bank. Preserve them against equivalent-register
   // merging: the 125 MHz control showed >94% routing delay on shared WADR.
   (* dont_touch="true" *) reg [8:0] write_offset,read_offset;
   reg [W-1:0] value;
   always @(posedge clk)begin
     if(rst||(!protect&&!pending))begin write_offset<=0;read_offset<=0;end
     else begin
       if(take_write&&written<CAPACITY)write_offset<=write_offset+1'b1;
       if(take_read)read_offset<=read_offset+1'b1;
     end
     if(take_write&&written<CAPACITY&&written[AW-1:9]==b)
       memory[write_offset]<=din;
     if(take_read)value<=memory[read_offset];
   end
   assign bank_q[b]=value;
 end endgenerate
 always @(posedge clk)begin
   if(rst)begin
     written<=0;requested<=0;read_valid<=0;pop_valid<=0;read_bank<=0;overflow<=0;
   end else begin
     read_valid<=take_read;pop_valid<=read_valid;
     if(take_read)begin read_bank<=requested[AW-1:9];requested<=requested+1;end
     if(read_valid)pop_data<=bank_q[read_bank];
     if(take_write)begin
       if(written==CAPACITY)overflow<=1;
       else written<=written+1;
     end
     if(!protect&&!pending)begin written<=0;requested<=0;end
   end
 end
endmodule
