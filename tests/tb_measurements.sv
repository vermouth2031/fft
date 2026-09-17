`timescale 1ns/1ps
module tb_measurements;
 reg clk=0;always #4 clk=~clk;
 reg rst=1,tv=0,finish=0,sv=0,last=0;
 reg [31:0] iq=0;reg [63:0] tick=0;
 always @(posedge clk)tick<=tick+1;
 wire wv,bv,rv,fault;wire [191:0] wd;wire [287:0] bd;wire [255:0] rd;wire [63:0] samples;
 time_measure tm(.clk(clk),.rst(rst),.valid(tv),.iq(iq),.tick(tick),.finish(finish),
 .ton(36'd1048576),.toff(36'd262144),.kon(16'd8),.koff(16'd32),.max_burst(32'd1048576),
 .window_valid(wv),.window_data(wd),.burst_valid(bv),.burst_data(bd),.samples(samples));
 reg [47:0] data=0;reg [23:0] user=0;
 spectrum_measure sm(.clk(clk),.rst(rst),.data(data),.user(user),.valid(sv),.last(last),
 .roi_low(13'd0),.roi_high(13'd8191),.result_valid(rv),.result_data(rd),.fault(fault),
 .snap_request(1'b0),.snap_we(),.snap_addr(),.snap_data(),.snap_done(),.snap_window());
 reg [31:0] iqvec[0:524287],counts[0:7];reg [287:0] bgold[0:6];
 reg [63:0] fftvec[0:98303];reg [255:0] sgold[0:11];
 integer c,n,bursts=0,spectra=0,windows=0;
 always @(posedge clk)if(!rst)begin
   if(bv)begin
     if(bursts>=7||bd!==bgold[bursts])$fatal(1,"burst %0d got=%h expected=%h",bursts,bd,bgold[bursts]);
     bursts=bursts+1;
   end
   if(wv)windows=windows+1;
   if(rv)begin
     if(spectra>=12||rd!==sgold[spectra])$fatal(1,"spectrum %0d got=%h expected=%h",spectra,rd,sgold[spectra]);
     spectra=spectra+1;
   end
   if(fault)$fatal(1,"spectrum bank overwrite");
 end
 initial begin
   $readmemh("test_iq.mem",iqvec);$readmemh("time_expected.mem",bgold);$readmemh("time_counts.mem",counts);
   $readmemh("spectrum_input.mem",fftvec);$readmemh("spectrum_expected.mem",sgold);
   for(c=0;c<8;c=c+1)begin
     @(negedge clk);rst=1;tv=0;finish=0;repeat(8)@(negedge clk);rst=0;
     for(n=0;n<32768;n=n+1)begin
       // Gaps test sample-index semantics independently of source clock time.
       if(n%257==0)begin @(negedge clk);tv=0;repeat(2)@(negedge clk);end
       @(negedge clk);tv=1;iq=iqvec[c*32768+n];
     end
     @(negedge clk);tv=0;finish=1;
     @(negedge clk);finish=0;repeat(20)@(negedge clk);
     if(bursts!=counts[c]||samples!=32768)$fatal(1,"time case %0d counts",c);
   end
   if(windows!=32)$fatal(1,"window count");
   @(negedge clk);rst=1;repeat(8)@(negedge clk);rst=0;
   for(n=0;n<98304;n=n+1)begin
     @(negedge clk);sv=1;data=fftvec[n][47:0];user={8'd0,fftvec[n][63:48]};last=(n%8192==8191);
   end
   @(negedge clk);sv=0;last=0;
   wait(spectra==12);repeat(10)@(negedge clk);
   $display("MEASUREMENTS_PASS time_cases=8 gap_samples=262144 spectra=12 continuous_bins=98304");$finish;
 end
 initial begin #6000000;$fatal(1,"measurement timeout");end
endmodule
