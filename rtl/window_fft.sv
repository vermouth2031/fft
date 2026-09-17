`timescale 1ns/1ps
module window_fft(input wire clk,rst,input wire hann,
 input wire [31:0] iq,input wire valid,output wire ready,
 output wire [47:0] fft_data,output wire [23:0] fft_user,
 output wire fft_valid,fft_last,output wire configured,
 output wire [5:0] events);
 (* rom_style="block" *) reg [17:0] hann_rom[0:8191];
 initial $readmemh("hann_u18_f17.mem",hann_rom);
 reg [12:0] index;
 reg [2:0] v,l;
 reg signed [15:0] i0,q0;
 reg signed [18:0] coeff;
 reg signed [34:0] pi,pq;
 reg [47:0] din;
 wire fft_ready,cfg_ready;
 reg cfg_valid,cfg_done;
 wire ce=!v[2]||fft_ready;
 assign ready=ce&&cfg_done;
 assign configured=cfg_done;
 function automatic [23:0] round_even(input signed [34:0] x);
   reg signed [34:0] y;
   begin y=(x>>>9)+((x[8:0]>9'd256)||((x[8:0]==9'd256)&&x[9]));round_even=y[23:0];end
 endfunction
 always @(posedge clk) begin
   if(rst) begin index<=0;v<=0;l<=0;cfg_valid<=1;cfg_done<=0;i0<=0;q0<=0;coeff<=0;pi<=0;pq<=0;din<=0;end
   else begin
     if(cfg_valid&&cfg_ready) begin cfg_valid<=0;cfg_done<=1;end
     if(ce) begin
       v<={v[1:0],valid&&ready};l<={l[1:0],index==8191};
       i0<=$signed(iq[15:0]);q0<=$signed(iq[31:16]);
       coeff<=hann?{1'b0,hann_rom[index]}:19'd131072;
       pi<=i0*coeff;pq<=q0*coeff;
       din<={round_even(pq),round_even(pi)};
       if(valid&&ready) index<=index+1;
     end
   end
 end
 wire [7:0] status;
 wire status_valid;
 fft8192 fft(.aclk(clk),.aresetn(!rst),
   .s_axis_config_tdata(16'h3557),.s_axis_config_tvalid(cfg_valid),.s_axis_config_tready(cfg_ready),
   .s_axis_data_tdata(din),.s_axis_data_tvalid(v[2]),.s_axis_data_tready(fft_ready),.s_axis_data_tlast(l[2]),
   .m_axis_data_tdata(fft_data),.m_axis_data_tuser(fft_user),.m_axis_data_tvalid(fft_valid),.m_axis_data_tready(1'b1),.m_axis_data_tlast(fft_last),
   .m_axis_status_tdata(status),.m_axis_status_tvalid(status_valid),.m_axis_status_tready(1'b1),
   .event_frame_started(),.event_tlast_unexpected(events[0]),.event_tlast_missing(events[1]),
   .event_fft_overflow(events[2]),.event_status_channel_halt(events[3]),
   .event_data_in_channel_halt(events[4]),.event_data_out_channel_halt(events[5]));
endmodule
