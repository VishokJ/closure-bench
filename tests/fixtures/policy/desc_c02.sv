// P2: receiver overrun. A second word (8'hA5) lands while the first is
// still pending and the sink is not ready: overrun_error pulses with
// m_axis_tvalid still high.
module cov_P2 (
  input logic       clk,
  input logic       rst,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  P2_rx_overrun_error: cover property (@(posedge clk) disable iff (rst)
    overrun_error && m_axis_tvalid && !m_axis_tready && (m_axis_tdata == 8'hA5));

endmodule

bind uart_rx cov_P2 u_cov_P2 (.*);
