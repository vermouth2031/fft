`timescale 1ns/1ps
// Two ping-pong spectra, each split into eight 1024x48 RAM lanes.
// All bins contribute to the CDF; snapshots retain the maximum of each 8 bins.
module spectrum_measure(input wire clk,rst,input wire [47:0] data,
 input wire [23:0] user,input wire valid,last,input wire [12:0] roi_low,roi_high,
 output reg result_valid,output reg [255:0] result_data,output reg fault,
 output reg snap_we,output reg [9:0] snap_addr,output reg [63:0] snap_data,
 input wire snap_request,output reg snap_done,output reg [31:0] snap_window);
 reg signed [47:0] rr,ii;
 reg [47:0] power,roi_power;
 reg [12:0] q0,q1,q2;
 reg [2:0] v,l,ov;
 reg write_bank;
 reg [63:0] total;
 reg [47:0] peak;
 reg [12:0] peakq;
 reg overflow;
 reg [31:0] frame;
 reg [1:0] bank_ready;
 reg [63:0] bank_total[0:1];
 reg [47:0] bank_peak[0:1];
 reg [12:0] bank_q[0:1];
 reg bank_overflow[0:1];
 reg [31:0] bank_frame[0:1];
 (* ram_style="block" *) reg [47:0] b00[0:1023],b01[0:1023],b02[0:1023],b03[0:1023],b04[0:1023],b05[0:1023],b06[0:1023],b07[0:1023];
 (* ram_style="block" *) reg [47:0] b10[0:1023],b11[0:1023],b12[0:1023],b13[0:1023],b14[0:1023],b15[0:1023],b16[0:1023],b17[0:1023];
 wire in_roi=q1>=roi_low&&q1<=roi_high;
 // Register the ROI-masked power before accumulation/peak selection. This
 // breaks the config -> ROI comparison -> peak comparison path. Carry the
 // bin index and all qualifiers through the same stage (one added clock).
 wire [47:0] wp=roi_power;
 wire [63:0] tnext=total+{16'b0,wp};
 wire better=wp>peak||(wp==peak&&q2<peakq);
 wire [47:0] pnext=better?wp:peak;
 wire [12:0] qnext=better?q2:peakq;
 localparam WAIT_BANK=0,DIV_START=1,DIV_WAIT=2,SCAN=3,PUBLISH=4;
 reg [2:0] state;
 reg read_bank;
 reg [63:0] rt,rpeak,lower,upper,cdf;
 reg [31:0] rid,rflags;
 reg [15:0] rq,lowq,highq;
 reg found_low,found_high;
 reg [10:0] request_count;
 reg [9:0] response_addr;
 reg response_valid;
 reg [47:0] a[0:7],b[0:7],power_pipe[0:7];
 reg [48:0] pair_prefix[0:7];
 reg [49:0] quad_prefix[0:7];
 reg [50:0] prefix[0:7];
 reg [47:0] pair_max[0:3],quad_max[0:1],octet_max;
 reg [63:0] cdf_bin[0:7];
 reg pipe_valid,pair_valid,quad_valid,prefix_valid,compare_valid;
 reg [9:0] pipe_addr,pair_addr,quad_addr,prefix_addr,compare_addr;
 wire scan_request=state==SCAN&&request_count<1024;
 integer j;
 wire div_done;
 wire [63:0] quotient,remainder;
 udiv64 div200(.clk(clk),.rst(rst),.start(state==DIV_START),.numerator(rt),.denominator(64'd200),
   .busy(),.done(div_done),.divide_by_zero(),.quotient(quotient),.remainder(remainder));
 reg capturing,snap_armed;
 // No RAM reset: a bank is completely written before it becomes ready.
 always @(posedge clk) begin
   if(v[2]&&!rst) begin
     if(!write_bank) begin
       case(q2[2:0])
         0:b00[q2[12:3]]<=wp;
         1:b01[q2[12:3]]<=wp;
         2:b02[q2[12:3]]<=wp;
         3:b03[q2[12:3]]<=wp;
         4:b04[q2[12:3]]<=wp;
         5:b05[q2[12:3]]<=wp;
         6:b06[q2[12:3]]<=wp;
         7:b07[q2[12:3]]<=wp;
       endcase
     end else begin
       case(q2[2:0])
         0:b10[q2[12:3]]<=wp;
         1:b11[q2[12:3]]<=wp;
         2:b12[q2[12:3]]<=wp;
         3:b13[q2[12:3]]<=wp;
         4:b14[q2[12:3]]<=wp;
         5:b15[q2[12:3]]<=wp;
         6:b16[q2[12:3]]<=wp;
         7:b17[q2[12:3]]<=wp;
       endcase
     end
   end
   if(scan_request&&!read_bank)begin
     a[0]<=b00[request_count[9:0]];
     a[1]<=b01[request_count[9:0]];
     a[2]<=b02[request_count[9:0]];
     a[3]<=b03[request_count[9:0]];
     a[4]<=b04[request_count[9:0]];
     a[5]<=b05[request_count[9:0]];
     a[6]<=b06[request_count[9:0]];
     a[7]<=b07[request_count[9:0]];
   end
   if(scan_request&&read_bank)begin
     b[0]<=b10[request_count[9:0]];
     b[1]<=b11[request_count[9:0]];
     b[2]<=b12[request_count[9:0]];
     b[3]<=b13[request_count[9:0]];
     b[4]<=b14[request_count[9:0]];
     b[5]<=b15[request_count[9:0]];
     b[6]<=b16[request_count[9:0]];
     b[7]<=b17[request_count[9:0]];
   end
 end
 always @(posedge clk) begin
   result_valid<=0;snap_we<=0;snap_done<=0;
   if(rst) begin
     rr<=0;ii<=0;power<=0;roi_power<=0;q0<=0;q1<=0;q2<=0;v<=0;l<=0;ov<=0;write_bank<=0;
     total<=0;peak<=0;peakq<=8191;overflow<=0;frame<=0;bank_ready<=0;
     state<=WAIT_BANK;read_bank<=0;rt<=0;rpeak<=0;rid<=0;rflags<=0;rq<=0;
     lower<=0;upper<=0;cdf<=0;lowq<=0;highq<=0;found_low<=0;found_high<=0;
     request_count<=0;response_valid<=0;response_addr<=0;fault<=0;result_data<=0;
     capturing<=0;snap_armed<=1;snap_addr<=0;snap_data<=0;snap_window<=0;
     // Datapath contents are ignored until their reset-cleared valid bits
     // advance. Leave these wide payload registers unreset to remove
     // the measured synchronized-reset fanout bottleneck.
     pipe_valid<=0;pair_valid<=0;quad_valid<=0;prefix_valid<=0;compare_valid<=0;
     pipe_addr<=0;pair_addr<=0;quad_addr<=0;prefix_addr<=0;compare_addr<=0;
   end else begin
     rr<=$signed(data[23:0])*$signed(data[23:0]);ii<=$signed(data[47:24])*$signed(data[47:24]);
     power<=rr+ii;q0<=user[12:0]^13'd4096;q1<=q0;
     roi_power<=in_roi?power:48'd0;q2<=q1;
     v<={v[1:0],valid};l<={l[1:0],last};ov<={ov[1:0],user[16]};
     if(v[2]) begin
       if(bank_ready[write_bank]||(state!=WAIT_BANK&&read_bank==write_bank)) fault<=1;
       if(l[2]) begin
         bank_total[write_bank]<=tnext;bank_peak[write_bank]<=pnext;bank_q[write_bank]<=qnext;
         bank_overflow[write_bank]<=overflow|ov[2];bank_frame[write_bank]<=frame;
         bank_ready[write_bank]<=1;write_bank<=!write_bank;frame<=frame+1;
         total<=0;peak<=0;peakq<=8191;overflow<=0;
       end else begin total<=tnext;peak<=pnext;peakq<=qnext;overflow<=overflow|ov[2];end
     end
     if(!snap_request) snap_armed<=1;
     response_valid<=scan_request;
     if(scan_request)begin response_addr<=request_count[9:0];request_count<=request_count+1;end
     // Registered balanced inclusive prefixes: 2 bins, 4 bins, 8 bins.
     // Only one 64-bit adder lies on the running-CDF feedback path.
     pipe_valid<=response_valid;pair_valid<=pipe_valid;quad_valid<=pair_valid;
     prefix_valid<=quad_valid;compare_valid<=prefix_valid;
     if(response_valid)begin
       for(j=0;j<8;j=j+1)power_pipe[j]<=read_bank?b[j]:a[j];
       pipe_addr<=response_addr;
     end
     if(pipe_valid)begin
       for(j=0;j<8;j=j+1)begin
         if(j%2==0)pair_prefix[j]<={1'b0,power_pipe[j]};
         else pair_prefix[j]<={1'b0,power_pipe[j-1]}+{1'b0,power_pipe[j]};
       end
       for(j=0;j<4;j=j+1)pair_max[j]<=power_pipe[j*2]>power_pipe[j*2+1]?power_pipe[j*2]:power_pipe[j*2+1];
       pair_addr<=pipe_addr;
     end
     if(pair_valid)begin
       for(j=0;j<8;j=j+1)begin
         if(j%4<2)quad_prefix[j]<={1'b0,pair_prefix[j]};
         else quad_prefix[j]<={1'b0,pair_prefix[(j/4)*4+1]}+{1'b0,pair_prefix[j]};
       end
       for(j=0;j<2;j=j+1)quad_max[j]<=pair_max[j*2]>pair_max[j*2+1]?pair_max[j*2]:pair_max[j*2+1];
       quad_addr<=pair_addr;
     end
     if(quad_valid)begin
       for(j=0;j<8;j=j+1)begin
         if(j<4)prefix[j]<={1'b0,quad_prefix[j]};
         else prefix[j]<={1'b0,quad_prefix[3]}+{1'b0,quad_prefix[j]};
       end
       octet_max<=quad_max[0]>quad_max[1]?quad_max[0]:quad_max[1];
       prefix_addr<=quad_addr;
     end
     if(prefix_valid)begin
       cdf<=cdf+{13'b0,prefix[7]};
       for(j=0;j<8;j=j+1)cdf_bin[j]<=cdf+{13'b0,prefix[j]};
       compare_addr<=prefix_addr;
       if(capturing)begin snap_we<=1;snap_addr<=prefix_addr;snap_data<={16'b0,octet_max};end
     end
     case(state)
       WAIT_BANK: if(bank_ready!=0) begin
         read_bank<=bank_ready[0]?0:1;
         rt<=bank_total[bank_ready[0]?0:1];rpeak<={16'b0,bank_peak[bank_ready[0]?0:1]};
         rq<={3'b0,bank_q[bank_ready[0]?0:1]};rid<=bank_frame[bank_ready[0]?0:1];
         rflags<=bank_overflow[bank_ready[0]?0:1]?32'd2:0;
         bank_ready[bank_ready[0]?0:1]<=0;state<=DIV_START;
         cdf<=0;found_low<=0;found_high<=0;lowq<=0;highq<=0;request_count<=0;
         capturing<=snap_request&&snap_armed;
         if(snap_request&&snap_armed)snap_armed<=0;
       end
       DIV_START: state<=DIV_WAIT;
       DIV_WAIT: if(div_done) begin lower<=quotient+(remainder!=0);upper<=rt-quotient;state<=SCAN;end
       SCAN: if(compare_valid)begin
         if(!found_low&&rt!=0)begin
           if(cdf_bin[0]>=lower)begin lowq<={3'b0,compare_addr,3'd0};found_low<=1;end
           else if(cdf_bin[1]>=lower)begin lowq<={3'b0,compare_addr,3'd1};found_low<=1;end
           else if(cdf_bin[2]>=lower)begin lowq<={3'b0,compare_addr,3'd2};found_low<=1;end
           else if(cdf_bin[3]>=lower)begin lowq<={3'b0,compare_addr,3'd3};found_low<=1;end
           else if(cdf_bin[4]>=lower)begin lowq<={3'b0,compare_addr,3'd4};found_low<=1;end
           else if(cdf_bin[5]>=lower)begin lowq<={3'b0,compare_addr,3'd5};found_low<=1;end
           else if(cdf_bin[6]>=lower)begin lowq<={3'b0,compare_addr,3'd6};found_low<=1;end
           else if(cdf_bin[7]>=lower)begin lowq<={3'b0,compare_addr,3'd7};found_low<=1;end
         end
         if(!found_high&&rt!=0)begin
           if(cdf_bin[0]>=upper)begin highq<={3'b0,compare_addr,3'd0};found_high<=1;end
           else if(cdf_bin[1]>=upper)begin highq<={3'b0,compare_addr,3'd1};found_high<=1;end
           else if(cdf_bin[2]>=upper)begin highq<={3'b0,compare_addr,3'd2};found_high<=1;end
           else if(cdf_bin[3]>=upper)begin highq<={3'b0,compare_addr,3'd3};found_high<=1;end
           else if(cdf_bin[4]>=upper)begin highq<={3'b0,compare_addr,3'd4};found_high<=1;end
           else if(cdf_bin[5]>=upper)begin highq<={3'b0,compare_addr,3'd5};found_high<=1;end
           else if(cdf_bin[6]>=upper)begin highq<={3'b0,compare_addr,3'd6};found_high<=1;end
           else if(cdf_bin[7]>=upper)begin highq<={3'b0,compare_addr,3'd7};found_high<=1;end
         end
         if(compare_addr==1023)state<=PUBLISH;
       end
       PUBLISH: begin
         result_valid<=1;
         result_data<={rflags|(rt==0?32'd1:0)|(rt!=0&&lowq==highq?32'd32:0)|
           (rt!=0&&(lowq==roi_low||highq==roi_high)?32'd16:0),rid,rt,rpeak[47:0],rq,lowq,highq,32'd0};
         if(capturing)begin snap_done<=1;snap_window<=rid;end
         state<=WAIT_BANK;
       end
     endcase
   end
 end
endmodule
