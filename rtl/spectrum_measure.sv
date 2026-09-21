`timescale 1ns/1ps
// Two spectra, each split into even/odd RAMs: one write or two reads/clock.
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
 (* ram_style="block" *) reg [47:0] b00[0:2047],b01[0:2047],b02[0:2047],b03[0:2047],b10[0:2047],b11[0:2047],b12[0:2047],b13[0:2047];
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
 reg [11:0] request_count;
 reg [10:0] response_addr;
 reg response_valid;
 reg [47:0] a0,a1,a2,a3,c0,c1,c2,c3;
 wire [47:0] pa=read_bank?c0:a0,pb=read_bank?c1:a1,pc=read_bank?c2:a2,pd=read_bank?c3:a3;
 reg [47:0] pa_pipe,pb_pipe,pc_pipe,pd_pipe,first_power,third_power;
 reg [48:0] pair01,pair23;
 reg [47:0] pairmax01,pairmax23,quad_max;
 reg [49:0] prefix0,prefix1,prefix2,prefix3;
 reg [63:0] cdf0,cdf1,cdf2,cdf3;
 reg pipe_valid,pair_valid,prefix_valid,compare_valid;
 reg [10:0] pipe_addr,pair_addr,prefix_addr,compare_addr;
 wire scan_request=state==SCAN&&request_count<2048;
 wire div_done;
 wire [63:0] quotient,remainder;
 udiv64 div200(.clk(clk),.rst(rst),.start(state==DIV_START),.numerator(rt),.denominator(64'd200),
   .busy(),.done(div_done),.divide_by_zero(),.quotient(quotient),.remainder(remainder));
 reg capturing,snap_armed;
 reg [47:0] group_max;
 wire [47:0] group_next=prefix_addr[0]==0?quad_max:(quad_max>group_max?quad_max:group_max);
 // No RAM reset: each bank is fully overwritten before becoming ready.
 always @(posedge clk) begin
   if(v[2]&&!rst) begin
     if(!write_bank) begin
       case(q2[1:0])
         0:b00[q2[12:2]]<=wp;1:b01[q2[12:2]]<=wp;
         2:b02[q2[12:2]]<=wp;3:b03[q2[12:2]]<=wp;
       endcase
     end else begin
       case(q2[1:0])
         0:b10[q2[12:2]]<=wp;1:b11[q2[12:2]]<=wp;
         2:b12[q2[12:2]]<=wp;3:b13[q2[12:2]]<=wp;
       endcase
     end
   end
   if(scan_request&&!read_bank) begin
     a0<=b00[request_count[10:0]];a1<=b01[request_count[10:0]];
     a2<=b02[request_count[10:0]];a3<=b03[request_count[10:0]];
   end
   if(scan_request&&read_bank) begin
     c0<=b10[request_count[10:0]];c1<=b11[request_count[10:0]];
     c2<=b12[request_count[10:0]];c3<=b13[request_count[10:0]];
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
     capturing<=0;snap_armed<=1;group_max<=0;snap_addr<=0;snap_data<=0;snap_window<=0;
     pa_pipe<=0;pb_pipe<=0;pc_pipe<=0;pd_pipe<=0;first_power<=0;third_power<=0;
     pair01<=0;pair23<=0;pairmax01<=0;pairmax23<=0;quad_max<=0;
     prefix0<=0;prefix1<=0;prefix2<=0;prefix3<=0;cdf0<=0;cdf1<=0;cdf2<=0;cdf3<=0;
     pipe_valid<=0;pair_valid<=0;prefix_valid<=0;compare_valid<=0;
     pipe_addr<=0;pair_addr<=0;prefix_addr<=0;compare_addr<=0;
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
     if(scan_request) begin response_addr<=request_count[10:0];request_count<=request_count+1;end
     // RAM -> data -> two pair sums -> four prefixes -> CDF -> comparisons.
     // CDF feedback has a single 64-bit adder. Snapshots still cover 8 bins.
     pipe_valid<=response_valid;pair_valid<=pipe_valid;prefix_valid<=pair_valid;compare_valid<=prefix_valid;
     if(response_valid)begin
       pa_pipe<=pa;pb_pipe<=pb;pc_pipe<=pc;pd_pipe<=pd;pipe_addr<=response_addr;
     end
     if(pipe_valid)begin
       first_power<=pa_pipe;third_power<=pc_pipe;
       pair01<={1'b0,pa_pipe}+{1'b0,pb_pipe};pair23<={1'b0,pc_pipe}+{1'b0,pd_pipe};
       pairmax01<=pa_pipe>pb_pipe?pa_pipe:pb_pipe;pairmax23<=pc_pipe>pd_pipe?pc_pipe:pd_pipe;
       pair_addr<=pipe_addr;
     end
     if(pair_valid)begin
       prefix0<={2'b0,first_power};prefix1<={1'b0,pair01};
       prefix2<={1'b0,pair01}+{2'b0,third_power};prefix3<={1'b0,pair01}+{1'b0,pair23};
       quad_max<=pairmax01>pairmax23?pairmax01:pairmax23;prefix_addr<=pair_addr;
     end
     if(prefix_valid)begin
       cdf<=cdf+{14'b0,prefix3};
       cdf0<=cdf+{14'b0,prefix0};cdf1<=cdf+{14'b0,prefix1};
       cdf2<=cdf+{14'b0,prefix2};cdf3<=cdf+{14'b0,prefix3};compare_addr<=prefix_addr;
       group_max<=group_next;
       if(capturing&&prefix_addr[0])begin snap_we<=1;snap_addr<=prefix_addr[10:1];snap_data<={16'b0,group_next};end
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
       SCAN: if(compare_valid) begin
         if(!found_low&&rt!=0) begin
           if(cdf0>=lower) begin lowq<={3'b0,compare_addr,2'd0};found_low<=1;end
           else if(cdf1>=lower) begin lowq<={3'b0,compare_addr,2'd1};found_low<=1;end
           else if(cdf2>=lower) begin lowq<={3'b0,compare_addr,2'd2};found_low<=1;end
           else if(cdf3>=lower) begin lowq<={3'b0,compare_addr,2'd3};found_low<=1;end
         end
         if(!found_high&&rt!=0) begin
           if(cdf0>=upper) begin highq<={3'b0,compare_addr,2'd0};found_high<=1;end
           else if(cdf1>=upper) begin highq<={3'b0,compare_addr,2'd1};found_high<=1;end
           else if(cdf2>=upper) begin highq<={3'b0,compare_addr,2'd2};found_high<=1;end
           else if(cdf3>=upper) begin highq<={3'b0,compare_addr,2'd3};found_high<=1;end
         end
         if(compare_addr==2047) state<=PUBLISH;
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
