// Near miss: the overrun word 8'hC3 is accepted on the very cycle the
// overrun pulses (m_axis_tready high), so there is no stalled overrun first.
module cov_P8_twin (
  input logic       clk,
  input logic       rst,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  P8_twin_overrun_accepted_same_cycle: cover property (@(posedge clk) disable iff (rst)
    overrun_error && m_axis_tvalid && m_axis_tready && (m_axis_tdata == 8'hC3));

endmodule

bind uart_rx cov_P8_twin u_cov_P8_twin (.*);
