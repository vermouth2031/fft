`timescale 1ns/1ps
module window_fft(input wire clk,rst,input wire hann,
 input wire [31:0] iq,input wire valid,output wire ready,
 output wire [47:0] fft_data,output wire [23:0] fft_user,
 output wire fft_valid,fft_last,output wire configured,
 output wire [5:0] events);
 localparam integer N=iq_build_config::FFT_LENGTH, LOGN=iq_build_config::FFT_LOG2;
 // Read independent 512-entry distributed ROM banks in the existing first
 // stage. Select their output in the existing coefficient stage: no extra
 // input latency and no full-depth asynchronous ROM mux on one clock path.
 localparam integer ROM_BANKS=N/2048,ROM_BANK_BITS=$clog2(ROM_BANKS);
 (* rom_style="distributed" *) reg [17:0] hann_rom[0:N/4-1];
 initial $readmemh("hann_quarter_u18_f17.mem",hann_rom);
 reg [LOGN-1:0] index;
 // The low bits are the position within a quarter. Odd quarters reverse
 // this position. A single short negation replaces two serial full-width
 // fold/subtract/mux operations. Quarter endpoints use the exact half value.
 wire [LOGN-3:0] quarter_offset=index[LOGN-3:0];
 wire [LOGN-3:0] quarter_index=index[LOGN-2]?-quarter_offset:quarter_offset;
 wire complement=index[LOGN-1]^index[LOGN-2];
 wire midpoint=index[LOGN-2]&&(quarter_offset==0);
 reg [17:0] rom_value[0:ROM_BANKS-1];
 reg [ROM_BANK_BITS-1:0] rom_bank;
 integer rb;
 reg complement0,midpoint0,hann0;
 reg [3:0] v,l;
 reg signed [15:0] i0,q0,i1,q1;
 reg signed [18:0] coeff;
 reg signed [34:0] pi,pq;
 reg [47:0] din;
 wire fft_ready,cfg_ready;
 reg cfg_valid,cfg_done;
 wire ce=!v[3]||fft_ready;
 assign ready=ce&&cfg_done;
 assign configured=cfg_done;
 function automatic [23:0] round_even(input signed [34:0] x);
   reg signed [34:0] y;
   begin y=(x>>>9)+((x[8:0]>9'd256)||((x[8:0]==9'd256)&&x[9]));round_even=y[23:0];end
 endfunction
 always @(posedge clk) begin
   if(rst) begin index<=0;v<=0;l<=0;cfg_valid<=1;cfg_done<=0;i0<=0;q0<=0;i1<=0;q1<=0;rom_bank<=0;complement0<=0;midpoint0<=0;hann0<=0;coeff<=0;pi<=0;pq<=0;din<=0;end
   else begin
     if(cfg_valid&&cfg_ready) begin cfg_valid<=0;cfg_done<=1;end
     if(ce) begin
       v<={v[2:0],valid&&ready};l<={l[2:0],index==N-1};
       i0<=$signed(iq[15:0]);q0<=$signed(iq[31:16]);
       for(rb=0;rb<ROM_BANKS;rb=rb+1)rom_value[rb]<=hann_rom[rb*512+quarter_index[8:0]];
       rom_bank<=quarter_index[LOGN-3:9];
       complement0<=complement;midpoint0<=midpoint;hann0<=hann;
       i1<=i0;q1<=q0;
       coeff<=!hann0?19'd131072:midpoint0?19'd65536:
              complement0?19'd131072-{1'b0,rom_value[rom_bank]}:{1'b0,rom_value[rom_bank]};
       pi<=i1*coeff;pq<=q1*coeff;
       din<={round_even(pq),round_even(pi)};
       if(valid&&ready) index<=index+1;
     end
   end
 end
 wire [7:0] status;
 wire status_valid;
 fft8192 fft(.aclk(clk),.aresetn(!rst),
   .s_axis_config_tdata(iq_build_config::FFT_CONFIG_WIDTH'(iq_build_config::FFT_CONFIG_WORD)),.s_axis_config_tvalid(cfg_valid),.s_axis_config_tready(cfg_ready),
   .s_axis_data_tdata(din),.s_axis_data_tvalid(v[3]),.s_axis_data_tready(fft_ready),.s_axis_data_tlast(l[3]),
   .m_axis_data_tdata(fft_data),.m_axis_data_tuser(fft_user),.m_axis_data_tvalid(fft_valid),.m_axis_data_tready(1'b1),.m_axis_data_tlast(fft_last),
   .m_axis_status_tdata(status),.m_axis_status_tvalid(status_valid),.m_axis_status_tready(1'b1),
   .event_frame_started(),.event_tlast_unexpected(events[0]),.event_tlast_missing(events[1]),
   .event_fft_overflow(events[2]),.event_status_channel_halt(events[3]),
   .event_data_in_channel_halt(events[4]),.event_data_out_channel_halt(events[5]));
endmodule
