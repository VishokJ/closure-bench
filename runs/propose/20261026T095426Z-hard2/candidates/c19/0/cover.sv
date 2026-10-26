// A pending word 8'h3C is accepted on the same clock that frame_error is high.
// On the next clock tvalid has dropped and tdata still holds 8'h3C.
module cov_P19 (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  P19_accept_during_frame_error: cover property (@(posedge clk) disable iff (rst)
    !$past(rst) && $past(frame_error) &&
    $past(m_axis_tvalid) && $past(m_axis_tready) && ($past(m_axis_tdata) == 8'h3C) &&
    !m_axis_tvalid && (m_axis_tdata == 8'h3C));

endmodule

bind uart_rx cov_P19 u_cov_P19 (.*);
