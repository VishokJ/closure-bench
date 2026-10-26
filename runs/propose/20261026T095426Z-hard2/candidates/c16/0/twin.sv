// Twin: same overrun of a stalled 8'h3C by 8'hA5, but with no frame error
// seen while 8'h3C was held (one step short of the sequence).
module cov_P16_twin (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  reg st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 1'b0;
    end else begin
      if (!m_axis_tvalid || m_axis_tready || m_axis_tdata != 8'h3C) begin
        st <= 1'b0;
      end else if (frame_error) begin
        st <= 1'b1;
      end
    end
  end

  P16_twin_overrun_without_frame_error: cover property (@(posedge clk) disable iff (rst)
    !st && overrun_error && m_axis_tvalid && (m_axis_tdata == 8'hA5) &&
    ($past(m_axis_tdata) == 8'h3C) && !$past(m_axis_tready));

endmodule

bind uart_rx cov_P16_twin u_cov_P16_twin (.*);
