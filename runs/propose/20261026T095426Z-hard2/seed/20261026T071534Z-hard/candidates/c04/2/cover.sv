// Two back-to-back frames, each with a two-edge glitch on rxd_reg inside a
// data-bit interval (bit_cnt 2..9) strictly between sample points
// (prescale_reg != 0). Both words must still arrive intact: 8'hA5, then 8'h5A.
module cov_P4 (
  input logic        clk,
  input logic        rst,
  input logic [3:0]  bit_cnt,
  input logic [18:0] prescale_reg,
  input logic        rxd_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata,
  input logic        frame_error,
  input logic        overrun_error
);

  reg       rxd_q;
  reg       tv_q;
  reg [1:0] cnt;    // edges of rxd_reg in the current sample interval (saturating)
  reg       seen;   // an off-sample glitch completed in this frame's data bits
  reg       stage;  // first glitched frame delivered 8'hA5

  always @(posedge clk) begin
    if (rst) begin
      rxd_q <= 1'b1;
      tv_q  <= 1'b0;
      cnt   <= 2'd0;
      seen  <= 1'b0;
      stage <= 1'b0;
    end else begin
      rxd_q <= rxd_reg;
      tv_q  <= m_axis_tvalid;
      if (prescale_reg == 19'd0) begin
        cnt <= 2'd0;
        if (bit_cnt >= 4'd2 && bit_cnt <= 4'd9 && cnt == 2'd2 && rxd_reg == rxd_q) begin
          seen <= 1'b1;
        end
        if (bit_cnt == 4'd0 && !rxd_reg) begin
          seen <= 1'b0;
        end
      end else if (bit_cnt >= 4'd2 && bit_cnt <= 4'd9 && rxd_reg != rxd_q && cnt != 2'd3) begin
        cnt <= cnt + 2'd1;
      end
      if (frame_error || overrun_error) begin
        stage <= 1'b0;
      end else if (m_axis_tvalid && !tv_q) begin
        if (seen && m_axis_tdata == 8'hA5) begin
          stage <= 1'b1;
        end else begin
          stage <= 1'b0;
        end
      end
    end
  end

  P4_rx_glitch_off_sample_point_ignored: cover property (@(posedge clk) disable iff (rst)
    stage && seen && m_axis_tvalid && !tv_q && (m_axis_tdata == 8'h5A) &&
    !frame_error && !overrun_error);

endmodule

bind uart_rx cov_P4 u_cov_P4 (.*);
