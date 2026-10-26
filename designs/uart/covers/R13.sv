// Resynchronisation after a framing error: the frame_error pulse coincides with
// rxd_reg low, so a new frame starts at once. That frame runs to completion
// (bit_cnt never back at 0 in between) and delivers 8'hA5.
module cov_R13 (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       rxd_reg,
  input logic [3:0] bit_cnt,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata
);

  reg st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 1'b0;
    end else begin
      if (st && bit_cnt == 4'd0 && !frame_error) begin
        st <= 1'b0;
      end
      if (frame_error && !rxd_reg) begin
        st <= 1'b1;
      end
    end
  end

  R13_rx_resync_after_frame_error: cover property (@(posedge clk) disable iff (rst)
    st && $rose(m_axis_tvalid) && (m_axis_tdata == 8'hA5));

endmodule

bind uart_rx cov_R13 u_cov_R13 (.*);
