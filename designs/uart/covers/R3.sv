// Overrun: a second good frame lands while the first word (8'h3C) is still
// unread with m_axis_tready low; the output register now holds 8'hA5.
module cov_R3 (
  input logic       clk,
  input logic       rst,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  R3_overrun_second_word: cover property (@(posedge clk) disable iff (rst)
    overrun_error && m_axis_tvalid && (m_axis_tdata == 8'hA5) &&
    ($past(m_axis_tdata) == 8'h3C) && !$past(m_axis_tready));

endmodule

bind uart_rx cov_R3 u_cov_R3 (.*);
