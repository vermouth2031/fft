`timescale 1ns/1ps
// Independent bin-domain oracle: no DUT internals or pipeline assumptions.
// Exercise FFT bit-reversed arrival order, ping-pong reuse, ROI and snapshot.
module tb_spectrum_edges;
 localparam CASES=12;
 reg clk=0;always #4 clk=~clk;
 reg rst=1,valid=0,last=0,snap_request=0;
 reg [47:0] data=0;
 reg [23:0] user=0;
 reg [12:0] roi_low=0,roi_high=8191;
 wire rv,fault,snap_we,snap_done;
 wire [255:0] rd;
 wire [9:0] snap_addr;
 wire [63:0] snap_data;
 wire [31:0] snap_window;
 spectrum_measure dut(.clk(clk),.rst(rst),.data(data),.user(user),
   .valid(valid),.last(last),.roi_low(roi_low),.roi_high(roi_high),
   .result_valid(rv),.result_data(rd),.fault(fault),.snap_we(snap_we),
   .snap_addr(snap_addr),.snap_data(snap_data),.snap_request(snap_request),
   .snap_done(snap_done),.snap_window(snap_window));

 reg [255:0] expected[0:CASES-1];
 reg [63:0] expected_snap[0:CASES*1024-1];
 reg [63:0] oracle_power[0:8191];
 integer captured_frame[0:5];
 integer results=0,snapshots=0,snap_words=0,cycles=0;
 integer last_cycle[0:CASES-1];
 integer minimum_latency=2147483647,maximum_latency=0;

 function automatic integer low_for(input integer f);
   if(f>=6&&f<=8)low_for=100;
   else if(f==9)low_for=4095;
   else if(f==11)low_for=7000;
   else low_for=0;
 endfunction
 function automatic integer high_for(input integer f);
   if(f>=6&&f<=8)high_for=7000;
   else if(f==9)high_for=4095;
   else if(f==11)high_for=100;
   else high_for=8191;
 endfunction
 function automatic integer real_for(input integer f,q);
   case(f)
     0:real_for=0;
     1:real_for=(q==0||q==8191)?4000:0;
     2:real_for=-8388608;
     3:real_for=q==4095?321:0; // The last arriving FFT bin, not the last scanned bin.
     4:real_for=((q*3571+12345)&65535)-32768;
     5:real_for=q==8191?17:0;
     6:real_for=(q==99||q==7001)?8388607:((q==100||q==7000)?100:0);
     7:real_for=q==100?13:(q==99?500:0);
     8:real_for=q==7000?19:(q==7001?500:0);
     9:real_for=-33;
     10:real_for=((q*8191+113)&16777215)-8388608;
     default:real_for=42;
   endcase
 endfunction
 function automatic integer imag_for(input integer f,q);
   case(f)
     2:imag_for=-8388608;
     4:imag_for=((q*971+753)&65535)-32768;
     9:imag_for=44;
     10:imag_for=((q*12289+997)&16777215)-8388608;
     default:imag_for=0;
   endcase
 endfunction
 function automatic bit overflow_for(input integer f,k);
   overflow_for=((f==1||f==3)&&k==8191)||(f==2&&k==0)||
                (f==4&&k==1234)||(f==6&&(k^4096)==99);
 endfunction
 function automatic integer reverse13(input integer value);
   integer bit_index;
   begin
     reverse13=0;
     for(bit_index=0;bit_index<13;bit_index=bit_index+1)
       reverse13=(reverse13<<1)|((value>>bit_index)&1);
   end
 endfunction
 function automatic bit capture_request_for(input integer f);
   capture_request_for=(f==0||f==1||f==3||f==5||f==7||f==9||f==11);
 endfunction

 task automatic build_oracle(input integer f);
   integer q,k,lo,hi,pkq,group_index;
   longint signed re,im;
   reg [63:0] total,pk,cdf,lower,upper,p;
   reg [31:0] flags;
   begin
     total=0;pk=0;pkq=0;flags=0;
     for(q=0;q<8192;q=q+1)begin
       re=real_for(f,q);im=imag_for(f,q);
       p=(q>=low_for(f)&&q<=high_for(f))?re*re+im*im:0;
       oracle_power[q]=p;total=total+p;
       // Ascending-bin argmax defines the lowest-bin tie rule independently
       // of the bit-reversed arrival order presented to the DUT.
       if(p>pk)begin pk=p;pkq=q;end
       k=q^4096;
       if(overflow_for(f,k))flags=flags|2;
     end
     lo=0;hi=0;cdf=0;lower=(total+199)/200;upper=total-total/200;
     if(total!=0)begin
       lo=-1;hi=-1;
       for(q=0;q<8192;q=q+1)begin
         cdf=cdf+oracle_power[q];
         if(lo==-1&&cdf>=lower)lo=q;
         if(hi==-1&&cdf>=upper)hi=q;
       end
     end
     if(total==0)flags=flags|1;
     else begin
       if(lo==hi)flags=flags|32;
       if(lo==low_for(f)||hi==high_for(f))flags=flags|16;
     end
     expected[f]={flags,32'(f),total,pk[47:0],16'(pkq),16'(lo),16'(hi),32'd0};
     for(group_index=0;group_index<1024;group_index=group_index+1)begin
       pk=0;
       for(q=group_index*8;q<group_index*8+8;q=q+1)
         if(oracle_power[q]>pk)pk=oracle_power[q];
       expected_snap[f*1024+group_index]=pk;
     end
   end
 endtask

 always @(posedge clk)begin
   cycles=cycles+1;
   if(!rst)begin
     if(fault)$fatal(1,"Unexpected spectrum bank overwrite");
     if(rv)begin
       if(results>=CASES)$fatal(1,"Unexpected extra spectrum");
       if(rd!==expected[results])
         $fatal(1,"Spectrum %0d got=%h expected=%h",results,rd,expected[results]);
       if(cycles-last_cycle[results]<minimum_latency)minimum_latency=cycles-last_cycle[results];
       if(cycles-last_cycle[results]>maximum_latency)maximum_latency=cycles-last_cycle[results];
       results=results+1;
     end
     if(snap_we)begin
       if(snapshots>=6)$fatal(1,"Unexpected extra snapshot");
       if(snap_addr!==10'(snap_words))$fatal(1,"Snapshot address %0d expected %0d",snap_addr,snap_words);
       if(snap_data!==expected_snap[captured_frame[snapshots]*1024+snap_words])
         $fatal(1,"Snapshot frame=%0d group=%0d got=%h expected=%h",captured_frame[snapshots],snap_words,
                   snap_data,expected_snap[captured_frame[snapshots]*1024+snap_words]);
       snap_words=snap_words+1;
     end
     if(snap_done)begin
       if(snapshots>=6||snap_words!=1024||snap_window!==32'(captured_frame[snapshots]))
         $fatal(1,"Snapshot completion: capture=%0d words=%0d window=%0d",snapshots,snap_words,snap_window);
       snapshots=snapshots+1;snap_words=0;
     end
   end
 end

 task automatic drive_frame(input integer f);
   integer n,k,q;
   reg signed [23:0] re,im;
   begin
     for(n=0;n<8192;n=n+1)begin
       // Invalid beats deliberately carry last/overflow and large data; none
       // may change bank completion, overflow flags, power, or bin indexing.
       if(f==10&&n%257==0)begin
         @(negedge clk);valid=0;last=1;user=24'h01ffff;data=48'h800000800000;
         repeat(2)@(negedge clk);
       end
       @(negedge clk);
       k=reverse13(n);q=k^4096;re=real_for(f,q);im=imag_for(f,q);
       valid=1;last=n==8191;data={im,re};user={7'd0,overflow_for(f,k),3'd0,13'(k)};
       // Previous frame's decision is taken within the first few pipeline
       // clocks; change request later, keeping consecutive frames gapless.
       if(n==8)snap_request=capture_request_for(f);
       if(last)last_cycle[f]=cycles+1;
     end
   end
 endtask

 integer f;
 initial begin
   captured_frame[0]=0;captured_frame[1]=3;captured_frame[2]=5;
   captured_frame[3]=7;captured_frame[4]=9;captured_frame[5]=11;
   for(f=0;f<CASES;f=f+1)build_oracle(f);
   repeat(8)@(negedge clk);rst=0;
   for(f=0;f<CASES;f=f+1)begin
     // ROI configuration is constant until all results using it have drained,
     // as required by the core's stopped-run configuration contract.
     if(f==6||f==9||f==10||f==11)begin
       @(negedge clk);valid=0;last=0;
       wait(results==f);repeat(8)@(negedge clk);
       roi_low=13'(low_for(f));roi_high=13'(high_for(f));
     end
     drive_frame(f);
   end
   @(negedge clk);valid=0;last=0;
   wait(results==CASES);repeat(100)@(negedge clk);
   if(snapshots!=6||snap_words!=0)$fatal(1,"Snapshot count %0d words %0d",snapshots,snap_words);
   $display("SPECTRUM_EDGES_PASS frames=%0d snapshot_words=%0d last_to_result_cycles=%0d..%0d",
            results,snapshots*1024,minimum_latency,maximum_latency);
   $finish;
 end
 initial begin #2000000;$fatal(1,"Spectrum edge test timeout");end
endmodule
