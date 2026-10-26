// Twin: same frame-error clock with the 8'h3C word pending, but tready is low,
// so the word is not accepted and tvalid stays high with tdata unchanged.
module cov_P19_twin (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  P19_twin_held_during_frame_error: cover property (@(posedge clk) disable iff (rst)
    !$past(rst) && $past(frame_error) &&
    $past(m_axis_tvalid) && !$past(m_axis_tready) && ($past(m_axis_tdata) == 8'h3C) &&
    m_axis_tvalid && (m_axis_tdata == 8'h3C));

endmodule

bind uart_rx cov_P19_twin u_cov_P19_twin (.*);
