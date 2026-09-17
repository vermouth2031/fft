`timescale 1ns/1ps
module tb_units;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,start=0;reg [63:0] num=0,den=1;
 wire sd,dd;wire [31:0] root;wire [63:0] q,r;
 isqrt64 sq(.clk(clk),.rst(rst),.start(start),.rad(num),.busy(),.done(sd),.root(root));
 udiv64 dv(.clk(clk),.rst(rst),.start(start),.numerator(num),.denominator(den),.busy(),.done(dd),.divide_by_zero(),.quotient(q),.remainder(r));
 reg [287:0] golden[0:255];
 reg push=0;reg [1023:0] record_data=0;reg [31:0] consumer=0;
 wire [31:0] producer,dropped,read_data;wire busy;reg [12:0] read_addr=0;
 record_ring ring(.clk(clk),.rst(rst),.push(push),.record_data(record_data),.consumer(consumer),.producer(producer),.dropped(dropped),.busy(busy),.read_addr(read_addr),.read_data(read_data));
 integer n,w;
 task push_record(input integer id);
   begin
     @(negedge clk);for(w=0;w<32;w=w+1)record_data[w*32+:32]=(id<<8)|w;push=1;
     @(negedge clk);push=0;repeat(35)@(negedge clk);
   end
 endtask
 initial begin
   $readmemh("math_vectors.mem",golden);repeat(4)@(negedge clk);rst=0;
   for(n=0;n<256;n=n+1)begin
     @(negedge clk);num=golden[n][287:224];den=golden[n][223:160];start=1;
     @(negedge clk);start=0;wait(sd);@(negedge clk);if(root!==golden[n][31:0])$fatal(1,"sqrt vector %d",n);
     wait(dd);@(negedge clk);if(q!==golden[n][159:96]||r!==golden[n][95:32])$fatal(1,"divide vector %d",n);
   end
   for(n=0;n<300;n=n+1)push_record(n);
   if(producer!=256||dropped!=44)$fatal(1,"full ring counts");
   for(n=0;n<8192;n=n+1)begin
     @(negedge clk);read_addr=n;repeat(2)@(negedge clk);
     if(read_data!==((n/32)<<8|(n%32)))$fatal(1,"unread record overwritten at %d",n);
   end
   consumer=256;push_record(300);
   if(producer!=257||dropped!=44)$fatal(1,"ring wrap");
   read_addr=0;repeat(2)@(negedge clk);if(read_data!=300*256)$fatal(1,"wrap data");
   $display("UNITS_PASS 256_math_vectors 300_queue_pushes full_no_overwrite wrap_release");$finish;
 end
 initial begin #2000000;$fatal(1,"unit timeout");end
endmodule
