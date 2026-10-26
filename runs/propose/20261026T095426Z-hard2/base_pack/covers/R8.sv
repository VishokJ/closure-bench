// Reset taken mid-frame after a word was delivered and handed off:
// the first reset edge must clear busy, tvalid and tdata.
module cov_R8 (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       busy
);

  R8_reset_midframe_clears_outputs: cover property (@(posedge clk)
    rst && $past(rst) &&
    $past(busy) && !$past(m_axis_tvalid) && ($past(m_axis_tdata) == 8'hA5) &&
    !busy && !m_axis_tvalid && (m_axis_tdata == 8'h00));

endmodule

bind uart_rx cov_R8 u_cov_R8 (.*);
