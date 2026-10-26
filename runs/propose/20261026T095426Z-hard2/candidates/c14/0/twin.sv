// Twin: the same 8'h5A frame arrives after the accepted 8'hA5, but with a high
// stop bit, so the word is delivered instead of discarded.
module cov_P14_twin (
  input logic       clk,
  input logic       rst,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata
);

  P14_twin_good_stop_delivers: cover property (@(posedge clk) disable iff (rst)
    m_axis_tvalid && !$past(m_axis_tvalid) &&
    (m_axis_tdata == 8'h5A) && ($past(m_axis_tdata) == 8'hA5));

endmodule

bind uart_rx cov_P14_twin u_cov_P14_twin (.*);
