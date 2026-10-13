`timescale 1ns/1ps
module tb_phase13_commit;
 reg clk=0;always #3.125 clk=~clk;
 reg rst=1,cancel=0,start=0,target=0;
 reg [31:0] length=16384,block_id=0,expected_crc=0,computed_crc=0,errors=0;
 wire finish,c0,c1,tq,busy;wire [31:0] lq,bq,cq,eq;
 iq_dma_commit dut(.clk(clk),.rst(rst),.cancel(cancel),.start(start),.target(target),
 .length(length),.block_id(block_id),.expected_crc(expected_crc),.computed_crc(computed_crc),.errors(errors),
 .finish(finish),.commit0(c0),.commit1(c1),.target_q(tq),.length_q(lq),.block_q(bq),.crc_q(cq),.error_q(eq),.busy(busy));
 reg invalidate=0,release_bank=0,host_ready=0,lwe=0,bwe=0,cwe=0;
 reg [31:0] hd=0;reg [3:0] hs=0;
 wire ready;wire [31:0] ml,mb,mc;
 iq_bank_metadata meta(.clk(clk),.rst(rst),.release_bank(release_bank),.invalidate(invalidate||cancel),
 .host_ready(host_ready),.host_length_we(lwe),.host_block_we(bwe),.host_crc_we(cwe),
 .host_data(hd),.host_strobe(hs),.commit((c0||c1)&&!cancel),
 .commit_length(lq),.commit_block(bq),.commit_crc(cq),.ready(ready),.length(ml),.block_id(mb),.crc(mc));
 integer count=0,i,j,expected_count;reg [31:0] saved_crc,saved_block;
 always @(posedge clk)if(!rst&&!cancel&&(c0||c1))count=count+1;
 task step;begin @(negedge clk);end endtask
 task launch(input integer id,input bit bad,input bit error_flag);
 begin
   step();invalidate=1;step();invalidate=0;
   target=(id/4)%2;length=16384;block_id=id;expected_crc=32'hcafe0000+id;
   computed_crc=expected_crc^(bad?32'h1:0);errors=error_flag?32'h8:0;
   saved_crc=computed_crc;saved_block=block_id;start=1;step();start=0;
   // Changing all live inputs after capture must not alter the transaction.
   target=~target;length=32768;block_id=32'hdeadbeef;expected_crc=0;computed_crc=0;errors=0;
 end endtask
 initial begin
   repeat(3)step();rst=0;
   for(i=0;i<64;i=i+1)begin
     expected_count=count+((i%4==0)?1:0);
     launch(i,i%4==1||i%4==3,i%4>=2);
     if(!busy||finish||ready)$fatal(1,"premature completion");
     step();if(finish||ready)$fatal(1,"validation published too early");
     step();if(!finish||tq!=((i/4)%2)||lq!=16384||bq!=saved_block||cq!=saved_crc)$fatal(1,"capture changed");
     if((c0||c1)!=(i%4==0)||(c0&&c1))$fatal(1,"incorrect routing");
     if(i%4==0&&(c0!==((i/4)%2==0)||c1!==((i/4)%2==1)))$fatal(1,"wrong bank committed");
     if(eq!=((i%4==1||i%4==3?32'h10:0)|(i%4>=2?32'h8:0)))$fatal(1,"incorrect error flags");
     step();if(count!=expected_count||ready!=(i%4==0))$fatal(1,"non-atomic commit");
     if(ready&&(ml!=16384||mb!=saved_block||mc!=saved_crc))$fatal(1,"metadata mismatch");
     repeat(3)step();if(count!=expected_count||finish||c0||c1)$fatal(1,"duplicate commit");
   end
   for(j=0;j<3;j=j+1)begin
     expected_count=count;launch(100+j,0,0);
     repeat(j)step();cancel=1;step();cancel=0;
     repeat(4)step();if(count!=expected_count||ready||busy||finish)$fatal(1,"cancel committed stage %d",j);
   end
   step();hd=32'h12345678;hs=15;lwe=1;bwe=1;cwe=1;step();
   hd=32'habcdef00;hs=5;step();lwe=0;bwe=0;cwe=0;
   if(ml!=32'h12cd5600||mb!=ml||mc!=ml)$fatal(1,"byte strobes");
   host_ready=1;step();host_ready=0;if(!ready)$fatal(1,"host ready");
   release_bank=1;step();release_bank=0;if(ready||ml!=32'h12cd5600)$fatal(1,"release metadata");
   $display("PHASE13_COMMIT_PASS transactions=64 cancel_stages=3 atomic_metadata byte_strobes captured_payload single_completion");$finish;
 end
 initial begin #20000;$fatal(1,"timeout");end
endmodule
