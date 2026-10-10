`timescale 1ns/1ps
// Compare the actual old/new window pipelines, including arbitrary bubbles,
// identical FFT backpressure, signed extremes, frame boundaries and resets.
// The sink stub deliberately does not test FFT arithmetic: tb_core does that
// separately against AMD's exact model in the final selected clock profile.
module tb_phase11_window;
 reg clk=0,rst=1,hann=0,valid=0; reg [31:0] iq=0,prng=32'h91a0031f;
 always #4 clk=~clk;
 wire ra,rb,va,vb,la,lb,ca,cb;wire[47:0] da,db;wire[23:0] ua,ub;wire[5:0] ea,eb;
 integer accepted=0,produced=0,total=0,mode,j;
 window_fft candidate(clk,rst,hann,iq,valid,ra,da,ua,va,la,ca,ea);
 phase10_window_fft baseline(clk,rst,hann,iq,valid,rb,db,ub,vb,lb,cb,eb);
 always @(posedge clk)begin
   if(rst)begin accepted=0;produced=0;end
   else begin
     if({ra,va,la,ca,ea}!=={rb,vb,lb,cb,eb})$fatal(1,"window control differs");
     if(va)begin
       if(da!==db)$fatal(1,"window data differs sample=%d got=%h expected=%h",produced,da,db);
       produced=produced+1;total=total+1;
     end
     if(valid&&ra)accepted=accepted+1;
   end
 end
 initial begin
   for(mode=0;mode<3;mode=mode+1)begin
     @(negedge clk);rst=1;valid=0;hann=mode!=0;
     repeat(5)@(negedge clk);rst=0;
     // Cover every coefficient twice in both windows, with changing signed IQ.
     while(accepted<2*iq_build_config::FFT_LENGTH)begin
       @(negedge clk);
       if(ra||!valid)begin
         prng={prng[30:0],prng[31]^prng[21]^prng[1]^prng[0]};
         valid=(prng[2:0]!=0)&&(accepted<2*iq_build_config::FFT_LENGTH);
         case(accepted%7)
           0:iq=32'h80008000;1:iq=32'h7fff7fff;2:iq=32'hffff0001;default:iq=prng;
         endcase
       end
     end
     @(negedge clk);valid=0;wait(produced==2*iq_build_config::FFT_LENGTH);
     // Reset a nonempty pipeline before the next run.
     for(j=0;j<17;j=j+1)begin @(negedge clk);valid=1;iq=prng;end
   end
   @(negedge clk);rst=1;valid=0;
   $display("PHASE11_WINDOW_EQUIVALENCE_PASS comparisons=%0d all_hann_indices_bubbles_backpressure_reset",total);
   $finish;
 end
 initial begin #5000000;$fatal(1,"window equivalence timeout");end
endmodule

module fft8192(input wire aclk,aresetn,input wire[15:0] s_axis_config_tdata,
 input wire s_axis_config_tvalid,output wire s_axis_config_tready,
 input wire[47:0] s_axis_data_tdata,input wire s_axis_data_tvalid,
 output wire s_axis_data_tready,input wire s_axis_data_tlast,
 output reg[47:0] m_axis_data_tdata,output wire[23:0] m_axis_data_tuser,
 output reg m_axis_data_tvalid,input wire m_axis_data_tready,output reg m_axis_data_tlast,
 output wire[7:0] m_axis_status_tdata,output wire m_axis_status_tvalid,input wire m_axis_status_tready,
 output wire event_frame_started,event_tlast_unexpected,event_tlast_missing,event_fft_overflow,
 event_status_channel_halt,event_data_in_channel_halt,event_data_out_channel_halt);
 reg[7:0] phase=0;
 assign s_axis_config_tready=1;
 assign s_axis_data_tready=phase[2:0]!=3 && phase[3:1]!=5;
 assign m_axis_data_tuser=0;
 assign m_axis_status_tdata=0;
 assign m_axis_status_tvalid=0;
 assign {event_frame_started,event_tlast_unexpected,event_tlast_missing,event_fft_overflow,
 event_status_channel_halt,event_data_in_channel_halt,event_data_out_channel_halt}=0;
 always @(posedge aclk)begin
   if(!aresetn)begin phase<=0;m_axis_data_tvalid<=0;m_axis_data_tlast<=0;m_axis_data_tdata<=0;end
   else begin
     phase<=phase+1;
     m_axis_data_tvalid<=s_axis_data_tvalid&&s_axis_data_tready;
     m_axis_data_tlast<=s_axis_data_tlast;
     if(s_axis_data_tvalid&&s_axis_data_tready)m_axis_data_tdata<=s_axis_data_tdata;
   end
 end
endmodule
