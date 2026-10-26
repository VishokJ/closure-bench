// Twin: same pending word under back-pressure, but the second frame's stop bit
// is high, so the frame completes as an overrun instead of a frame error.
module cov_P9_twin (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  P9_twin_good_stop_overrun: cover property (@(posedge clk) disable iff (rst)
    overrun_error && !frame_error && m_axis_tvalid &&
    $past(m_axis_tvalid) && !$past(m_axis_tready) && ($past(m_axis_tdata) == 8'h3C));

endmodule

bind uart_rx cov_P9_twin u_cov_P9_twin (.*);
