// Overrun pulse seen with the sink stalled; the next handshake must carry
// the newest word 8'hC3 with no further overrun in between.
module cov_P8 (
  input logic       clk,
  input logic       rst,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  reg armed;

  always @(posedge clk) begin
    if (rst) begin
      armed <= 1'b0;
    end else begin
      if (overrun_error) begin
        if (m_axis_tvalid && !m_axis_tready) armed <= 1'b1;
        else armed <= 1'b0;
      end else if (m_axis_tvalid && m_axis_tready) begin
        armed <= 1'b0;
      end
    end
  end

  P8_overrun_then_accept_newest: cover property (@(posedge clk) disable iff (rst)
    armed && !overrun_error && m_axis_tvalid && m_axis_tready &&
    (m_axis_tdata == 8'hC3));

endmodule

bind uart_rx cov_P8 u_cov_P8 (.*);
