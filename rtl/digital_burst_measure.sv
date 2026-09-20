`timescale 1ns/1ps
// Exact digital support detector for a zero-background I/Q stream. Indices
// advance only on valid samples. A completed interval excludes confirmation
// zeros; short interior zero runs remain in its length and RMS denominator.
// Forced segments cover the observed stream without gaps. Until GAP_MIN zeros
// confirm the end, even a zero-only continuation can be a timeout segment.
module digital_burst_measure(
 input wire clk,rst,enable,valid,finish,
 input wire [31:0] power,
 input wire [63:0] sample_index,
 input wire [15:0] gap_min,
 input wire [31:0] max_burst,
 output reg burst_valid,output reg [287:0] burst_data);
 localparam [31:0] DIGITAL_ZERO=32'h1000,START_UNCONFIRMED=32'h2000,
   CAPTURE_TRUNCATED=32'h100,DETECTOR_TIMEOUT=32'h400;
 reg active,start_unconfirmed,has_nonzero;
 reg [15:0] zeros;
 reg [31:0] length,peak,burst_id;
 reg [63:0] start_sample,last_nonzero,energy,observed_end;
 wire [63:0] energy_next=energy+{32'd0,power};
 wire [31:0] peak_next=power>peak?power:peak;
 wire [31:0] base_flags=DIGITAL_ZERO|(start_unconfirmed?START_UNCONFIRMED:0);

 task emit(input [63:0] ending,input [63:0] sum,input [31:0] maximum,input [31:0] flags);
   begin
     burst_valid<=1;
     burst_data<={flags,burst_id,start_sample,ending,sum,maximum};
     burst_id<=burst_id+1;
   end
 endtask

 always @(posedge clk)begin
   burst_valid<=0;
   if(rst||!enable)begin
     active<=0;start_unconfirmed<=0;has_nonzero<=0;zeros<=0;
     length<=0;peak<=0;burst_id<=0;start_sample<=0;last_nonzero<=0;
     energy<=0;observed_end<=0;burst_data<=0;
   end else begin
     if(valid)begin
       observed_end<=sample_index+1;
       if(power==0)begin
         if(zeros<gap_min)zeros<=zeros+1;
       end else begin zeros<=0;last_nonzero<=sample_index;end
       if(!active)begin
         if(power!=0)begin
           active<=1;start_sample<=sample_index;start_unconfirmed<=zeros<gap_min;
           length<=1;energy<={32'd0,power};peak<=power;has_nonzero<=1;
           if(max_burst==1)begin
             burst_valid<=1;
             burst_data<={DIGITAL_ZERO|DETECTOR_TIMEOUT|(zeros<gap_min?START_UNCONFIRMED:32'd0),
               burst_id,sample_index,sample_index+64'd1,32'd0,power,power};
             burst_id<=burst_id+1;
             start_sample<=sample_index+1;start_unconfirmed<=1;
             length<=0;energy<=0;peak<=0;has_nonzero<=0;
           end
         end
       end else begin
         // A confirmed gap wins if confirmation and the size limit coincide.
         if(power==0&&zeros>=gap_min-1)begin
           if(has_nonzero)emit(last_nonzero+1,energy,peak,base_flags);
           active<=0;length<=0;has_nonzero<=0;
         end else if(length+1>=max_burst)begin
           emit(sample_index+1,energy_next,peak_next,base_flags|DETECTOR_TIMEOUT);
           start_sample<=sample_index+1;start_unconfirmed<=1;
           length<=0;energy<=0;peak<=0;has_nonzero<=0;
         end else begin
           length<=length+1;energy<=energy_next;peak<=peak_next;
           if(power!=0)has_nonzero<=1;
         end
       end
     end
     // The caller delays finish until after the final power sample. The full
     // observed suffix, including unconfirmed zeros, determines the RMS length.
     if(finish&&!valid&&active)begin
       if(length!=0)emit(observed_end,energy,peak,base_flags|CAPTURE_TRUNCATED);
       active<=0;length<=0;has_nonzero<=0;
     end
   end
 end
endmodule
