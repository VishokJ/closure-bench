// tvalid rises on the end-of-stop-period clock (tready still low) right after
// a frame that shifted out 8'hC3; next clock: start bit on txd, tready high.
// The byte loaded there must then be shifted out completely as 8'h3C.
module cov_P20 (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        s_axis_tvalid,
  input logic        s_axis_tready
);

  reg       tvalid_q;
  reg [7:0] shift;
  reg       have;
  reg [1:0] ph;
  reg       done;

  always @(posedge clk) begin
    if (rst) begin
      tvalid_q <= 1'b0;
      shift    <= 8'h00;
      have     <= 1'b0;
      ph       <= 2'd0;
      done     <= 1'b0;
    end else begin
      tvalid_q <= s_axis_tvalid;
      done     <= 1'b0;
      if (ph == 2'd1) begin
        if (!txd && s_axis_tready) begin
          ph <= 2'd2;
        end else begin
          ph <= 2'd0;
        end
      end
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0) begin
        if (s_axis_tvalid) begin
          if (!tvalid_q && !s_axis_tready && have && shift == 8'hC3) begin
            ph <= 2'd1;
          end else begin
            ph <= 2'd0;
          end
          have  <= 1'b0;
          shift <= 8'h00;
        end
      end else if (prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
        shift <= {txd, shift[7:1]};
        if (bit_cnt == 4'd1) begin
          have <= 1'b1;
          if (ph == 2'd2) begin
            done <= 1'b1;
            ph   <= 2'd0;
          end
        end
      end
    end
  end

  P20_tvalid_rise_on_frame_end: cover property (@(posedge clk) disable iff (rst)
    done && shift == 8'h3C && txd && bit_cnt == 4'd0);

endmodule

bind uart_tx cov_P20 u_cov_P20 (.*);
