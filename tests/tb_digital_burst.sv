`timescale 1ns/1ps
module tb_digital_burst;
 reg clk=0;always #5 clk=~clk;
 reg rst=1,valid=0,finish=0;
 reg [31:0] iq=0,maximum=1048576;
 reg [15:0] gap=32;
 wire bv,wv;wire [287:0] bd;wire [63:0] samples;
 time_measure dut(.clk(clk),.rst(rst),.valid(valid),.iq(iq),.tick(64'd0),.finish(finish),
   .ton(36'd1048576),.toff(36'd262144),.kon(16'd8),.koff(16'd32),.max_burst(maximum),
   .detector_mode(1'b1),.gap_min(gap),.window_valid(wv),.window_data(),
   .burst_valid(bv),.burst_data(bd),.samples(samples));
 reg [287:0] expected[0:32767];
 integer fd,code,case_count,c,n,count=0,wcount=0,expected_count,sample_count;
 integer gap_value,maximum_value,simultaneous_finish;
 integer total_samples=0,total_bursts=0;
 reg [31:0] word;
 always @(posedge clk)if(!rst)begin
   if(bv)begin
     if(count>=expected_count||bd!==expected[count])
       $fatal(1,"digital case=%0d burst=%0d got=%h expected=%h",c,count,bd,expected[count]);
     if(bd[159:96]<=bd[223:160])$fatal(1,"empty/negative digital interval");
     count=count+1;total_bursts=total_bursts+1;
   end
   if(wv)wcount=wcount+1;
 end
 initial begin
   fd=$fopen("digital_cases.txt","r");if(fd==0)$fatal(1,"digital fixture missing");
   code=$fscanf(fd,"%d",case_count);if(code!=1)$fatal(1,"fixture header");
   for(c=0;c<case_count;c=c+1)begin
     @(negedge clk);rst=1;valid=0;finish=0;count=0;wcount=0;
     code=$fscanf(fd,"%d %d %d %d %d",sample_count,gap_value,maximum_value,expected_count,simultaneous_finish);
     if(code!=5||expected_count>32768)$fatal(1,"fixture case header %0d",c);
     gap=gap_value;maximum=maximum_value;
     for(n=0;n<expected_count;n=n+1)begin
       code=$fscanf(fd,"%h",expected[n]);if(code!=1)$fatal(1,"fixture expected");
     end
     repeat(8)@(negedge clk);rst=0;
     for(n=0;n<sample_count;n=n+1)begin
       // Deliberate bubbles carry arbitrary nonzero bus values. Neither the
       // sample index nor the zero-run counter may advance on invalid cycles.
       if(n%37==0)begin @(negedge clk);valid=0;iq=32'h80008000;repeat(2)@(negedge clk);end
       code=$fscanf(fd,"%h",word);if(code!=1)$fatal(1,"fixture sample");
       @(negedge clk);valid=1;iq=word;finish=simultaneous_finish&&n==sample_count-1;
     end
     @(negedge clk);valid=0;finish=!simultaneous_finish;
     @(negedge clk);finish=0;repeat(20)@(negedge clk);
     if(count!=expected_count||samples!=sample_count||wcount!=sample_count/8192)
       $fatal(1,"digital case=%0d count=%0d expected=%0d samples=%0d/%0d windows=%0d",c,count,expected_count,samples,sample_count,wcount);
     total_samples=total_samples+sample_count;
   end
   $fclose(fd);
   $display("DIGITAL_BURST_PASS cases=%0d samples=%0d bursts=%0d gaps full_scale finish_both_forms forced_segments valid_bubbles",case_count,total_samples,total_bursts);
   $finish;
 end
 initial begin #40000000;$fatal(1,"digital burst timeout");end
endmodule
