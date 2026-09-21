`timescale 1ns/1ps
module tb_core;
 reg src_clk=0,fft_clk=0;
 always #5 src_clk=~src_clk;
 always #4 fft_clk=~fft_clk;
 reg rst=1,valid=0,finish=0,hann=0;
 reg [31:0] iq=0;
 reg [63:0] tick=0;
 always @(posedge src_clk) tick<=tick+1;
 wire ready,fv,bv;wire [1023:0] frec;wire [511:0] brec;
 wire [63:0] samples;wire [31:0] completed,max_latency;wire [7:0] errors;
 analyzer_core dut(.src_clk(src_clk),.fft_clk(fft_clk),.rst(rst),.valid(valid),.iq(iq),.finish(finish),.tick(tick),
 .hann(hann),.roi_low(13'd0),.roi_high(13'd8191),.ton(36'd1048576),.toff(36'd262144),.kon(16'd8),.koff(16'd32),
 .max_burst(32'd1048576),.detector_mode(1'b0),.gap_min(16'd32),.epoch(32'd1),.config_id(32'd1),.ready(ready),.freq_valid(fv),.freq_record(frec),
 .burst_valid(bv),.burst_record(brec),.samples(samples),.completed(completed),.max_latency(max_latency),.errors(errors),
 .snap_request(1'b1),.snap_we(),.snap_addr(),.snap_data(),.snap_done(),.snap_window());
 reg [31:0] vectors[0:524287];reg [47:0] golden[0:524287];
 integer c=0,n,j,fd,bin_count=0,window_count=0,results=0,total_results=0;
 integer frame_out=0,k;
 // S5 diagnostics use one simulator timebase (ns), never subtract clock counters
 // from different domains. Events describe the edge at which each consumer acts.
 integer latency_fd,lat_input=0,lat_fft_bin=0,lat_fft_window=0;
 always @(posedge src_clk)begin
   if(rst)lat_input=0;
   else begin
     if(valid)begin
       if(lat_input%8192==0)$fwrite(latency_fd,"%0d,%0d,input_first,%0.3f\n",c,lat_input/8192,$realtime);
       if(lat_input%8192==8191)$fwrite(latency_fd,"%0d,%0d,input_last,%0.3f\n",c,lat_input/8192,$realtime);
       lat_input=lat_input+1;
     end
     if(dut.rb.state==9&&!dut.rb.is_burst)
       $fwrite(latency_fd,"%0d,%0d,analysis_done,%0.3f\n",c,dut.rb.cr[191:160],$realtime);
     if(fv)$fwrite(latency_fd,"%0d,%0d,record_observed,%0.3f\n",c,frec[3*32+:32],$realtime);
   end
 end
 always @(posedge fft_clk)begin
   if(dut.frst)begin lat_fft_bin=0;lat_fft_window=0;end
   else begin
     if(dut.fft_valid)begin
       if(lat_fft_bin==0)$fwrite(latency_fd,"%0d,%0d,fft_first,%0.3f\n",c,lat_fft_window,$realtime);
       if(dut.fft_last)begin
         $fwrite(latency_fd,"%0d,%0d,fft_last,%0.3f\n",c,lat_fft_window,$realtime);
         lat_fft_bin=0;lat_fft_window=lat_fft_window+1;
       end else lat_fft_bin=lat_fft_bin+1;
     end
     if(dut.sm.v[2]&&dut.sm.l[2])$fwrite(latency_fd,"%0d,%0d,bank_ready,%0.3f\n",c,dut.sm.frame,$realtime);
     if(dut.sm.scan_request&&dut.sm.request_count==0)$fwrite(latency_fd,"%0d,%0d,scan_first,%0.3f\n",c,dut.sm.rid,$realtime);
     if(dut.sm.state==3&&dut.sm.compare_valid&&dut.sm.compare_addr==4095)
       $fwrite(latency_fd,"%0d,%0d,scan_last,%0.3f\n",c,dut.sm.rid,$realtime);
     if(dut.sm.state==4)$fwrite(latency_fd,"%0d,%0d,scan_result,%0.3f\n",c,dut.sm.rid,$realtime);
   end
 end
 always @(posedge fft_clk)begin
   if(rst)begin frame_out=0;bin_count=0;end
   else if(dut.fft_valid)begin
     k=dut.fft_user[12:0];
     if(dut.fft_data!==golden[c*32768+frame_out*8192+k])begin
       $display("FFT_MISMATCH case=%0d frame=%0d k=%0d got=%h expected=%h",c,frame_out,k,dut.fft_data,golden[c*32768+frame_out*8192+k]);$fatal;
     end
     bin_count=bin_count+1;
     if(dut.fft_last)begin if(bin_count!=8192)$fatal(1,"bad FFT frame length");frame_out=frame_out+1;bin_count=0;end
   end
 end
 always @(posedge src_clk)begin
   if(!rst&&errors!=0)$fatal(1,"core errors=%h case=%0d",errors,c);
   if(!rst&&fv)begin
     $fwrite(fd,"F %0d",c);for(j=0;j<32;j=j+1)$fwrite(fd," %08x",frec[j*32+:32]);$fwrite(fd,"\n");
     results=results+1;total_results=total_results+1;
     if(frec[12*32+:32]>200000)$fatal(1,"2ms deadline exceeded");
   end
   if(!rst&&bv)begin
     $fwrite(fd,"B %0d",c);for(j=0;j<16;j=j+1)$fwrite(fd," %08x",brec[j*32+:32]);$fwrite(fd,"\n");
   end
 end
 initial begin
   $readmemh("test_iq.mem",vectors);$readmemh("golden_fft.mem",golden);fd=$fopen("core_results.txt","w");
   latency_fd=$fopen("latency_events.csv","w");$fwrite(latency_fd,"case,window,event,time_ns\n");
   for(c=0;c<16;c=c+1)begin
     @(negedge src_clk);rst=1;valid=0;finish=0;hann=c>=8;results=0;
     repeat(24)@(negedge src_clk);rst=0;wait(ready);
     for(n=0;n<32768;n=n+1)begin @(negedge src_clk);valid=1;iq=vectors[c*32768+n];end
     @(negedge src_clk);valid=0;finish=1;
     @(negedge src_clk);finish=0;
     wait(results==4);repeat(600)@(negedge src_clk);
     if(samples!=32768)$fatal(1,"sample count");
     $display("CASE_PASS case=%0d fft_frames=%0d results=%0d latency_cycles=%0d",c,frame_out,results,max_latency);
   end
   $fclose(fd);$fclose(latency_fd);$display("CORE_PASS cases=16 exact_fft_points=524288 frequency_records=%0d",total_results);$finish;
 end
 initial begin #15000000;$fatal(1,"timeout");end
endmodule
