`timescale 1ns/1ps
module time_measure(input wire clk,rst,input wire valid,input wire [31:0] iq,
 input wire [63:0] tick,input wire finish,
 input wire [35:0] ton,toff,input wire [15:0] kon,koff,input wire [31:0] max_burst,
 input wire detector_mode,input wire [15:0] gap_min,
 output reg window_valid,output reg [191:0] window_data,
 output wire burst_valid,output wire [287:0] burst_data,
 output reg [63:0] samples);
 reg [31:0] ii,qq,p;
 reg [1:0] pv;
 reg [5:0] finishing;
 reg [63:0] t0,t1;
 reg [63:0] energy,first_tick;
 reg [31:0] peak,window_id,burst_id;
 reg [12:0] window_pos;
 wire [63:0] enext=energy+{32'b0,p};
 wire [31:0] pnext=p>peak?p:peak;
 reg [31:0] history[0:15];
 reg [3:0] hp;
 reg [4:0] filled;
 reg [35:0] sliding;
 // Separate history subtraction, accumulator, threshold comparison and FSM.
 // The signed difference is at most +/-2^31; sign-extend before accumulation.
 reg signed [32:0] power_delta;
 reg [2:0] detector_valid;
 reg [31:0] p_delta,p_sum,p_detector;
 reg [63:0] n_delta,n_sum,n_detector;
 reg above_on,below_off;
 localparam IDLE=0,START_CAND=1,ACTIVE=2,END_CAND=3;
 reg [1:0] state;
 reg [15:0] confirm;
 reg [63:0] bs,be,benergy,tail_energy;
 reg [31:0] bpeak,tail_peak;
 // Length of the next detector sample, including start confirmation samples.
 reg [31:0] next_burst_length;
 wire [31:0] merged_peak=(bpeak>tail_peak?bpeak:tail_peak)>p_detector?(bpeak>tail_peak?bpeak:tail_peak):p_detector;
 reg threshold_burst_valid;reg [287:0] threshold_burst_data;
 wire digital_burst_valid;wire [287:0] digital_burst_data;
 digital_burst_measure digital_detector(.clk(clk),.rst(rst),.enable(detector_mode),
   .valid(pv[1]),.power(p),.sample_index(samples),.finish(finishing[2]),
   .gap_min(gap_min),.max_burst(max_burst),.burst_valid(digital_burst_valid),.burst_data(digital_burst_data));
 assign burst_valid=detector_mode?digital_burst_valid:threshold_burst_valid;
 assign burst_data=detector_mode?digital_burst_data:threshold_burst_data;
 task emit_burst(input [63:0] epos,input [63:0] e,input [31:0] pk,input [31:0] flags);
   begin
     threshold_burst_valid<=1;threshold_burst_data<={flags,burst_id,bs,epos,e,pk};
     burst_id<=burst_id+1;state<=IDLE;confirm<=0;
   end
 endtask
 always @(posedge clk) begin
   window_valid<=0;threshold_burst_valid<=0;
   if(rst) begin
     ii<=0;qq<=0;p<=0;pv<=0;finishing<=0;t0<=0;t1<=0;samples<=0;
     energy<=0;peak<=0;first_tick<=0;window_id<=0;window_pos<=0;window_data<=0;threshold_burst_data<=0;
     hp<=0;filled<=0;sliding<=0;state<=IDLE;confirm<=0;bs<=0;be<=0;benergy<=0;bpeak<=0;
     tail_energy<=0;tail_peak<=0;burst_id<=0;
     power_delta<=0;detector_valid<=0;p_delta<=0;p_sum<=0;p_detector<=0;
     n_delta<=0;n_sum<=0;n_detector<=0;above_on<=0;below_off<=0;
     next_burst_length<=0;
   end else begin
     pv<={pv[0],valid};finishing<={finishing[4:0],finish};
     detector_valid<={detector_valid[1:0],pv[1]};
     ii<=$signed(iq[15:0])*$signed(iq[15:0]);qq<=$signed(iq[31:16])*$signed(iq[31:16]);
     p<=ii+qq;t0<=tick;t1<=t0;
     if(pv[1]) begin
       samples<=samples+1;
       if(window_pos==0) first_tick<=t1;
       window_pos<=window_pos+1;
       if(window_pos==8191) begin
         window_valid<=1;window_data<={window_id,first_tick,enext,pnext};
         window_id<=window_id+1;energy<=0;peak<=0;
       end else begin energy<=enext;peak<=pnext;end
       history[hp]<=p;hp<=hp+1;if(filled<16) filled<=filled+1;
       power_delta<=$signed({1'b0,p})-$signed({1'b0,(filled==16?history[hp]:32'd0)});
       p_delta<=p;n_delta<=samples;
     end
     if(detector_valid[0])begin
       sliding<=sliding+{{3{power_delta[32]}},power_delta};
       p_sum<=p_delta;n_sum<=n_delta;
     end
     if(detector_valid[1])begin
       above_on<=sliding>ton;below_off<=sliding<toff;
       p_detector<=p_sum;n_detector<=n_sum;
     end
     if(detector_valid[2])begin
       if(state!=IDLE)next_burst_length<=next_burst_length+1;
       case(state)
         IDLE: if(above_on) begin
           bs<=n_detector;benergy<={32'b0,p_detector};bpeak<=p_detector;confirm<=1;
           next_burst_length<=2;
           state<=kon==1?ACTIVE:START_CAND;
           if(kon==1&&max_burst==1)begin
             threshold_burst_valid<=1;threshold_burst_data<={32'h400,burst_id,n_detector,n_detector+64'd1,32'd0,p_detector,p_detector};
             burst_id<=burst_id+1;state<=IDLE;confirm<=0;
           end
         end
         START_CAND: if(above_on) begin
           benergy<=benergy+p_detector;if(p_detector>bpeak)bpeak<=p_detector;confirm<=confirm+1;
           if(confirm+1>=kon)begin
             if(next_burst_length>=max_burst)emit_burst(n_detector+1,benergy+p_detector,p_detector>bpeak?p_detector:bpeak,32'h400);
             else state<=ACTIVE;
           end
         end else state<=IDLE;
         ACTIVE: begin
           if(next_burst_length>=max_burst) emit_burst(n_detector+1,benergy+p_detector,p_detector>bpeak?p_detector:bpeak,32'h400);
           else if(below_off) begin
             if(koff==1) emit_burst(n_detector,benergy,bpeak,0);
             else begin be<=n_detector;confirm<=1;tail_energy<=p_detector;tail_peak<=p_detector;state<=END_CAND;end
           end else begin benergy<=benergy+p_detector;if(p_detector>bpeak)bpeak<=p_detector;end
         end
         END_CAND: begin
           if(below_off && confirm+1>=koff) emit_burst(be,benergy,bpeak,0);
           else if(next_burst_length>=max_burst) emit_burst(n_detector+1,benergy+tail_energy+p_detector,merged_peak,32'h400);
           else if(below_off) begin
             confirm<=confirm+1;tail_energy<=tail_energy+p_detector;if(p_detector>tail_peak)tail_peak<=p_detector;
           end else begin benergy<=benergy+tail_energy+p_detector;bpeak<=merged_peak;state<=ACTIVE;end
         end
       endcase
     end
     // Finite replay closes an unconfirmed frame explicitly as truncated.
     if(finishing[5] && (state==ACTIVE||state==END_CAND))
       emit_burst(samples,benergy+(state==END_CAND?tail_energy:64'd0),
         state==END_CAND&&tail_peak>bpeak?tail_peak:bpeak,32'h100);
   end
 end
endmodule
