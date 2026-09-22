`timescale 1ns/1ps
module analyzer_core #(
 parameter integer SAMPLE_RATE_HZ=iq_build_config::SAMPLE_RATE_HZ)( input wire src_clk,fft_clk,input wire rst,
 input wire valid,input wire [31:0] iq,input wire finish,input wire [63:0] tick,
 input wire hann,input wire [12:0] roi_low,roi_high,input wire [35:0] ton,toff,
 input wire [15:0] kon,koff,input wire [31:0] max_burst,epoch,config_id,
 input wire detector_mode,input wire [15:0] gap_min,
 output wire ready,output wire fft_reset,output wire freq_valid,output wire [1023:0] freq_record,
 output wire burst_valid,output wire [511:0] burst_record,
 input wire diagnostic_toggle,
 output reg [63:0] accepted_samples,output reg [31:0] input_rejected,
 output reg [12:0] input_high_water,output wire diagnostic_arrived,
 output wire [223:0] fft_diagnostic,
 output wire [63:0] samples,output wire [31:0] completed,max_latency,output wire [7:0] errors,
 input wire snap_request,output wire snap_we,output wire [9:0] snap_addr,
 output wire [63:0] snap_data,output wire snap_done,output wire [31:0] snap_window);
 (* ASYNC_REG="TRUE" *) reg [2:0] core_reset=3'b111;
 // Register the OR/decode in its own domain before crossing it. This prevents
 // source-domain decode glitches reaching the first synchronizer stage.
 (* KEEP="TRUE" *) reg reset_launch=1'b1;
 always @(posedge src_clk)reset_launch<=rst;
 // Both edges enter the FFT clock through a synchronizer; in particular the
 // reverse FIFO reset is synchronous to its own 125 MHz write clock.
 always @(posedge fft_clk) core_reset<={core_reset[1:0],reset_launch};
 wire frst=core_reset[2];
 assign fft_reset=frst;
 wire [26:0] fft_config;
 xpm_cdc_array_single #(.WIDTH(27),.DEST_SYNC_FF(3),.SRC_INPUT_REG(1),.INIT_SYNC_FF(1)) config_cdc(
   .src_clk(src_clk),.src_in({hann,roi_low,roi_high}),.dest_clk(fft_clk),.dest_out(fft_config));
 wire [31:0] fifo_data;
 wire full,empty,wr_busy,rd_busy,fft_ready,configured;
 wire [47:0] fft_data;wire [23:0] fft_user;wire fft_valid,fft_last;
 wire [5:0] fft_events;
 wire [12:0] input_occupancy;
 wire accepted=valid&&!full&&!wr_busy;
 always @(posedge src_clk)begin
   if(rst)begin accepted_samples<=0;input_rejected<=0;input_high_water<=0;end
   else begin
     if(accepted)accepted_samples<=accepted_samples+1;
     if(valid&&!accepted)input_rejected<=input_rejected+1;
     if(input_occupancy>input_high_water)input_high_water<=input_occupancy;
   end
 end
 // Event counters live in their native clock domain. A request captures a
 // stable payload which is held until XPM acknowledges the transfer.
 (* ASYNC_REG="TRUE" *) reg [2:0] diagnostic_sync;
 reg diagnostic_seen,diagnostic_send;
 wire diagnostic_ack;
 reg [63:0] fft_input_samples,fft_output_samples;
 reg [31:0] fft_output_windows,result_queue_rejected,input_underreads;
 reg [223:0] diagnostic_payload;
 always @(posedge fft_clk)begin
   if(frst)begin
     diagnostic_sync<=0;diagnostic_seen<=0;diagnostic_send<=0;diagnostic_payload<=0;
     fft_input_samples<=0;fft_output_samples<=0;fft_output_windows<=0;
     result_queue_rejected<=0;input_underreads<=0;
   end else begin
     diagnostic_sync<={diagnostic_sync[1:0],diagnostic_toggle};
     if(fft_ready&&!empty&&!rd_busy)fft_input_samples<=fft_input_samples+1;
     if(fft_valid)fft_output_samples<=fft_output_samples+1;
     if(fft_valid&&fft_last)fft_output_windows<=fft_output_windows+1;
     if(raw_freq_valid&&(freq_full||freq_wbusy))result_queue_rejected<=result_queue_rejected+1;
     // FIFO read enable is guarded by !empty and !rd_busy; no underread is issued.
     if(!diagnostic_send&&!diagnostic_ack&&diagnostic_sync[2]!=diagnostic_seen)begin
       diagnostic_payload<={input_underreads,result_queue_rejected,fft_output_windows,fft_output_samples,fft_input_samples};
       diagnostic_seen<=diagnostic_sync[2];diagnostic_send<=1;
     end else if(diagnostic_ack)diagnostic_send<=0;
   end
 end
 xpm_cdc_handshake #(.WIDTH(224),.DEST_EXT_HSK(0),.DEST_SYNC_FF(3),.SRC_SYNC_FF(3),.INIT_SYNC_FF(1)) diagnostic_cdc(
 .src_clk(fft_clk),.src_in(diagnostic_payload),.src_send(diagnostic_send),.src_rcv(diagnostic_ack),
 .dest_clk(src_clk),.dest_out(fft_diagnostic),.dest_req(diagnostic_arrived),.dest_ack(1'b0));
 xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"),.FIFO_WRITE_DEPTH(4096),.WRITE_DATA_WIDTH(32),.READ_DATA_WIDTH(32),
 .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),.CDC_SYNC_STAGES(2),.DOUT_RESET_VALUE("0"),.USE_ADV_FEATURES("0004"),.WR_DATA_COUNT_WIDTH(13)) input_fifo(
 .wr_data_count(input_occupancy),.rst(rst),.wr_clk(src_clk),.wr_en(accepted),.din(iq),.full(full),.wr_rst_busy(wr_busy),
 .rd_clk(fft_clk),.rd_en(fft_ready&&!empty&&!rd_busy),.dout(fifo_data),.empty(empty),.rd_rst_busy(rd_busy),
 .sleep(1'b0),.injectsbiterr(1'b0),.injectdbiterr(1'b0));
 window_fft transform(.clk(fft_clk),.rst(frst),.hann(fft_config[26]),.iq(fifo_data),.valid(!empty&&!rd_busy),.ready(fft_ready),
 .fft_data(fft_data),.fft_user(fft_user),.fft_valid(fft_valid),.fft_last(fft_last),.configured(configured),.events(fft_events));
 wire raw_window_valid,raw_burst_valid;
 wire [191:0] raw_window,ctx_data;wire [287:0] raw_burst,burst_data;
 wire ctx_full,ctx_empty,ctx_pop,burst_full,burst_empty,burst_pop;
 time_measure tm(.clk(src_clk),.rst(rst),.valid(valid),.iq(iq),.tick(tick),.finish(finish),
 .ton(ton),.toff(toff),.kon(kon),.koff(koff),.max_burst(max_burst),.detector_mode(detector_mode),.gap_min(gap_min),
 .window_valid(raw_window_valid),.window_data(raw_window),.burst_valid(raw_burst_valid),.burst_data(raw_burst),.samples(samples));
 small_fifo #(.W(192),.AW(4)) contexts(.clk(src_clk),.rst(rst),.push(raw_window_valid),.din(raw_window),.full(ctx_full),.pop(ctx_pop),.dout(ctx_data),.empty(ctx_empty));
 small_fifo #(.W(288),.AW(4)) bursts(.clk(src_clk),.rst(rst),.push(raw_burst_valid),.din(raw_burst),.full(burst_full),.pop(burst_pop),.dout(burst_data),.empty(burst_empty));
 wire raw_freq_valid,spec_fault;
 wire [255:0] raw_freq,freq_data;
 wire freq_full,freq_empty,freq_pop,freq_wbusy,freq_rbusy;
 (* ASYNC_REG="TRUE" *) reg [1:0] snap_sync;
 always @(posedge fft_clk) if(frst)snap_sync<=0;else snap_sync<={snap_sync[0],snap_request};
 spectrum_measure sm(.clk(fft_clk),.rst(frst),.data(fft_data),.user(fft_user),.valid(fft_valid),.last(fft_last),
 .roi_low(fft_config[25:13]),.roi_high(fft_config[12:0]),.result_valid(raw_freq_valid),.result_data(raw_freq),.fault(spec_fault),
 .snap_request(snap_sync[1]),.snap_we(snap_we),.snap_addr(snap_addr),.snap_data(snap_data),.snap_done(snap_done),.snap_window(snap_window));
 xpm_fifo_async #(.FIFO_MEMORY_TYPE("distributed"),.FIFO_WRITE_DEPTH(16),.WRITE_DATA_WIDTH(256),.READ_DATA_WIDTH(256),
 .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),.CDC_SYNC_STAGES(2),.DOUT_RESET_VALUE("0"),.USE_ADV_FEATURES("0000")) freq_cdc(
 .rst(frst),.wr_clk(fft_clk),.wr_en(raw_freq_valid&&!freq_full&&!freq_wbusy),.din(raw_freq),.full(freq_full),.wr_rst_busy(freq_wbusy),
 .rd_clk(src_clk),.rd_en(freq_pop&&!freq_empty&&!freq_rbusy),.dout(freq_data),.empty(freq_empty),.rd_rst_busy(freq_rbusy),
 .sleep(1'b0),.injectsbiterr(1'b0),.injectdbiterr(1'b0));
 wire metadata_error;
 wire [31:0] integrity_flags=(errors[0]?32'h4:0)|(|{errors[6:4],errors[3:1]&3'b101}?32'h40:0)|
   (errors[5]||errors[2]?32'h80:0)|(errors[7]?32'h2:0);
 result_builder #(.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)) rb(.clk(src_clk),.rst(rst),.tick(tick),.epoch(epoch),.config_id(config_id),.hann(hann),.integrity_flags(integrity_flags),
 .ctx(ctx_data),.ctx_empty(ctx_empty),.ctx_pop(ctx_pop),.freq(freq_data),.freq_empty(freq_empty||freq_rbusy),.freq_pop(freq_pop),
 .burst(burst_data),.burst_empty(burst_empty),.burst_pop(burst_pop),.freq_valid(freq_valid),.freq_record(freq_record),
 .burst_valid(burst_valid),.burst_record(burst_record),.completed(completed),.max_latency(max_latency),.metadata_error(metadata_error));
 reg [3:0] src_error,core_error;
 (* ASYNC_REG="TRUE" *) reg [3:0] err_sync1,err_sync2;
 (* ASYNC_REG="TRUE" *) reg [1:0] cfg_sync;
 always @(posedge src_clk) begin
   if(rst)begin src_error<=0;err_sync1<=0;err_sync2<=0;cfg_sync<=0;end
   else begin
     src_error<=src_error|{metadata_error,raw_burst_valid&&burst_full,raw_window_valid&&ctx_full,valid&&(full||wr_busy)};
     err_sync1<=core_error;err_sync2<=err_sync1;cfg_sync<={cfg_sync[0],configured};
   end
 end
 always @(posedge fft_clk)begin
   if(frst)core_error<=0;
   else core_error<=core_error|{fft_events[2],|{fft_events[5],fft_events[3],fft_events[1:0]},raw_freq_valid&&(freq_full||freq_wbusy),spec_fault};
 end
 assign errors={err_sync2,src_error};
 assign ready=cfg_sync[1]&&!wr_busy&&!full;
endmodule
