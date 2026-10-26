// Frame error while an unread word (8'h3C) is pending under back-pressure:
// the pending word must survive untouched and no overrun is reported.
module cov_P9 (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  P9_frame_error_with_pending_word: cover property (@(posedge clk) disable iff (rst)
    frame_error && !overrun_error && m_axis_tvalid && (m_axis_tdata == 8'h3C) &&
    $past(m_axis_tvalid) && !$past(m_axis_tready) && ($past(m_axis_tdata) == 8'h3C));

endmodule

bind uart_rx cov_P9 u_cov_P9 (.*);
