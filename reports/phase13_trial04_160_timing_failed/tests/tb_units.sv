`timescale 1ns/1ps
module tb_units;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,start=0;reg [63:0] num=0,den=1;
 wire sd,dd;wire [31:0] root;wire [63:0] q,r;
 isqrt64 sq(.clk(clk),.rst(rst),.start(start),.rad(num),.busy(),.done(sd),.root(root));
 udiv64 dv(.clk(clk),.rst(rst),.start(start),.numerator(num),.denominator(den),.busy(),.done(dd),.divide_by_zero(),.quotient(q),.remainder(r));
 wire dc,zc;wire [63:0] qc,rc;
 udiv64 #(.DIVISOR_WIDTH(8)) constant_divider(.clk(clk),.rst(rst),.start(start),
 .numerator(num),.denominator(8'd200),.busy(),.done(dc),.divide_by_zero(zc),.quotient(qc),.remainder(rc));
 reg [287:0] golden[0:255];
 reg push=0;reg [1023:0] record_data=0;reg [31:0] consumer=0;
 wire [31:0] producer,dropped,read_data;wire busy;reg [12:0] read_addr=0;
 record_ring ring(.clk(clk),.rst(rst),.push(push),.record_data(record_data),.consumer(consumer),.producer(producer),.dropped(dropped),.busy(busy),.read_addr(read_addr),.read_data(read_data));
 integer n,w;
 reg [31:0] test_producer=0;
 wire [31:0] test_occupancy=test_producer-consumer;
 record_ring #(.WORDS_LOG2(4),.RECORDS_LOG2(7)) ring128(.clk(clk),.rst(rst),.push(1'b0),
 .record_data(512'd0),.consumer(consumer),.producer(),.dropped(),.busy(),.read_addr(11'd0),.read_data());
 task push_record(input integer id);
   begin
     @(negedge clk);for(w=0;w<32;w=w+1)record_data[w*32+:32]=(id<<8)|w;push=1;
     @(negedge clk);push=0;repeat(35)@(negedge clk);
   end
 endtask
 initial begin
   $readmemh("math_vectors.mem",golden);
   // Both actual ring sizes: all low-byte positions, full/empty boundaries,
   // invalid future consumers, and producer/consumer wrap at 2^32.
   force ring.producer=test_producer;force ring128.producer=test_producer;
   for(n=0;n<4096;n=n+1)begin
     consumer=32'hfffff000+n;
     for(w=-1;w<=257;w=w+1)begin
       test_producer=consumer+w;#1;
       if(ring.has_space!==(test_occupancy<256)||ring128.has_space!==(test_occupancy<128))
         $fatal(1,"ring capacity equivalence p=%h c=%h",test_producer,consumer);
     end
   end
   release ring.producer;release ring128.producer;consumer=0;
   repeat(4)@(negedge clk);rst=0;
   for(n=0;n<256;n=n+1)begin
     @(negedge clk);num=golden[n][287:224];den=golden[n][223:160];start=1;
     @(negedge clk);start=0;wait(sd);@(negedge clk);if(root!==golden[n][31:0])$fatal(1,"sqrt vector %d",n);
     wait(dd);@(negedge clk);if(q!==golden[n][159:96]||r!==golden[n][95:32])$fatal(1,"divide vector %d",n);
     if(!dc||zc||qc!==num/64'd200||rc!==num%64'd200)$fatal(1,"constant divider vector %d",n);
   end
   // Every possible remainder near zero and near the largest 64-bit input,
   // with the same done edge and exact result as the original 64/64 divider.
   for(n=0;n<800;n=n+1)begin
     @(negedge clk);num=n<400?64'(n):64'hffffffffffffffff-64'(n-400);den=200;start=1;
     @(negedge clk);start=0;wait(dd);@(negedge clk);
     if(!dc||zc||qc!==q||rc!==r||qc!==num/64'd200||rc!==num%64'd200)
       $fatal(1,"constant divider boundary %d",n);
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
   $display("UNITS_PASS 256_math_vectors 1056_constant_division_cases 300_queue_pushes full_no_overwrite wrap_release 1060864_capacity_pairs_both_ring_sizes");$finish;
 end
 initial begin #3000000;$fatal(1,"unit timeout");end
endmodule
