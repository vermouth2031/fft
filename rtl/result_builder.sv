`timescale 1ns/1ps
module result_builder(input wire clk,rst,input wire [63:0] tick,
 input wire [31:0] epoch,config_id,input wire hann,input wire [31:0] integrity_flags,
 input wire [191:0] ctx,input wire ctx_empty,output reg ctx_pop,
 input wire [255:0] freq,input wire freq_empty,output reg freq_pop,
 input wire [287:0] burst,input wire burst_empty,output reg burst_pop,
 output reg freq_valid,output reg [1023:0] freq_record,
 output reg burst_valid,output reg [511:0] burst_record,
 output reg [31:0] completed,max_latency,output reg metadata_error);
 localparam IDLE=0,PEAK_START=1,PEAK_WAIT=2,DIV_INT_START=3,DIV_INT_WAIT=4,
 DIV_FRAC_START=5,DIV_FRAC_WAIT=6,RMS_START=7,RMS_WAIT=8,PUBLISH=9;
 reg [3:0] state;
 reg is_burst;
 reg [191:0] cr;
 reg [255:0] fr;
 reg [287:0] br;
 reg [63:0] sqrt_rad,div_num,div_den,mean_int,mean_rem,rms_rad;
 reg [31:0] peak_result,rms_result;
 wire sqrt_done,div_done;
 wire [31:0] sqrt_root;
 wire [63:0] div_q,div_r;
 wire [63:0] burst_length=br[159:96]-br[223:160];
 wire [63:0] latency=tick-cr[159:96];
 isqrt64 sqrt(.clk(clk),.rst(rst),.start(state==PEAK_START||state==RMS_START),.rad(sqrt_rad),.busy(),.done(sqrt_done),.root(sqrt_root));
 udiv64 divide(.clk(clk),.rst(rst),.start(state==DIV_INT_START||state==DIV_FRAC_START),
 .numerator(div_num),.denominator(div_den),.busy(),.done(div_done),.divide_by_zero(),.quotient(div_q),.remainder(div_r));
 // Fs/N = 390625/32 exactly. Three registered stages avoid a long
 // add/multiply/round chain; results settle while the two roots execute.
 reg signed [14:0] dp,dl,dh,dc;
 reg [13:0] dw;
 reg signed [34:0] pp,pl,ph,pc;
 reg [33:0] pw;
 reg [31:0] hz_peak,hz_low,hz_high,hz_center,hz_width;
 function automatic [31:0] round_hz(input signed [34:0] x,input center);
   reg signed [34:0] biased;
   begin biased=x+(center?35'sd32:35'sd16)-(x[34]?35'sd1:35'sd0);
     round_hz=biased>>>(center?6:5);end
 endfunction
 always @(posedge clk)begin
   dp<=$signed({2'd0,fr[76:64]})-15'sd4096;
   dl<=$signed({2'd0,fr[60:48]})-15'sd4096;
   dh<=$signed({2'd0,fr[44:32]})-15'sd4096;
   dc<=$signed({2'd0,fr[60:48]})+$signed({2'd0,fr[44:32]})-15'sd8192;
   dw<={1'b0,fr[44:32]}-{1'b0,fr[60:48]};
   pp<=dp*20'sd390625;pl<=dl*20'sd390625;ph<=dh*20'sd390625;pc<=dc*20'sd390625;pw<=dw*20'd390625;
   hz_peak<=round_hz(pp,0);hz_low<=round_hz(pl,0);hz_high<=round_hz(ph,0);hz_center<=round_hz(pc,1);
   hz_width<=(pw+34'd16)>>5;
 end
 always @(posedge clk) begin
   freq_valid<=0;burst_valid<=0;ctx_pop<=0;freq_pop<=0;burst_pop<=0;
   if(rst) begin
     state<=IDLE;is_burst<=0;cr<=0;fr<=0;br<=0;sqrt_rad<=0;div_num<=0;div_den<=0;
     mean_int<=0;mean_rem<=0;rms_rad<=0;peak_result<=0;rms_result<=0;
     freq_record<=0;burst_record<=0;completed<=0;max_latency<=0;metadata_error<=0;
   end else case(state)
     IDLE: if(!freq_empty&&!ctx_empty) begin
       cr<=ctx;fr<=freq;ctx_pop<=1;freq_pop<=1;is_burst<=0;
       sqrt_rad<={ctx[31:0],32'd0};state<=PEAK_START;
       if(ctx[191:160]!=freq[223:192])metadata_error<=1;
     end else if(!burst_empty) begin
       br<=burst;burst_pop<=1;is_burst<=1;sqrt_rad<={burst[31:0],32'd0};state<=PEAK_START;
     end
     PEAK_START: state<=PEAK_WAIT;
     PEAK_WAIT: if(sqrt_done) begin
       peak_result<=sqrt_root;
       if(is_burst) begin div_num<=br[95:32];div_den<=burst_length;state<=DIV_INT_START;end
       else begin sqrt_rad<=cr[95:32]<<19;state<=RMS_START;end
     end
     DIV_INT_START: state<=DIV_INT_WAIT;
     DIV_INT_WAIT: if(div_done) begin
       mean_int<=div_q;mean_rem<=div_r;div_num<=div_r<<32;state<=DIV_FRAC_START;
     end
     DIV_FRAC_START:state<=DIV_FRAC_WAIT;
     DIV_FRAC_WAIT:if(div_done)begin sqrt_rad<=(mean_int<<32)|div_q;state<=RMS_START;end
     RMS_START:state<=RMS_WAIT;
     RMS_WAIT:if(sqrt_done)begin rms_result<=sqrt_root;state<=PUBLISH;end
     PUBLISH: begin
       if(is_burst) begin
         burst_record[0*32+:32]<=32'h42525331;burst_record[1*32+:32]<=br[287:256];
         burst_record[2*32+:32]<=epoch;burst_record[3*32+:32]<=br[255:224];
         burst_record[4*32+:32]<=config_id;burst_record[5*32+:32]<=100000000;
         burst_record[6*32+:64]<=br[223:160];burst_record[8*32+:64]<=br[159:96];
         burst_record[10*32+:32]<=burst_length[31:0];burst_record[11*32+:32]<=peak_result;
         burst_record[12*32+:32]<=rms_result;burst_record[13*32+:64]<=br[95:32];
         burst_record[15*32+:32]<=br[255:224];burst_valid<=1;
       end else begin
         freq_record[0*32+:32]<=32'h46525131;
         freq_record[1*32+:32]<=fr[255:224]|integrity_flags|(cr[191:160]!=fr[223:192]?32'h40:0);
         freq_record[2*32+:32]<=epoch;freq_record[3*32+:32]<=fr[223:192];
         freq_record[4*32+:32]<=config_id;freq_record[5*32+:32]<=100000000;
         freq_record[6*32+:64]<={19'd0,cr[191:160],13'd0};freq_record[8*32+:64]<=cr[159:96];
         freq_record[10*32+:64]<=tick;freq_record[12*32+:32]<=latency[31:0];
         freq_record[13*32+:32]<=8192;
         freq_record[14*32+:32]<=fr[224]?0:hz_peak;
         freq_record[15*32+:32]<=fr[224]?0:hz_low;
         freq_record[16*32+:32]<=fr[224]?0:hz_high;
         freq_record[17*32+:32]<=fr[224]?0:hz_width;
         freq_record[18*32+:32]<=fr[224]?0:hz_center;
         freq_record[19*32+:32]<={fr[63:48],fr[79:64]};freq_record[20*32+:32]<={16'd0,fr[47:32]};
         freq_record[21*32+:32]<=peak_result;freq_record[22*32+:32]<=rms_result;
         freq_record[23*32+:64]<=fr[191:128];freq_record[25*32+:64]<={16'd0,fr[127:80]};
         freq_record[27*32+:64]<=cr[95:32];freq_record[29*32+:32]<={7'd0,hann,8'd14,8'd24,8'd16};
         freq_record[30*32+:32]<=0;freq_record[31*32+:32]<=completed;
         completed<=completed+1;freq_valid<=1;
         if(latency>max_latency)max_latency<=latency[31:0];
       end
       state<=IDLE;
     end
   endcase
 end
endmodule
