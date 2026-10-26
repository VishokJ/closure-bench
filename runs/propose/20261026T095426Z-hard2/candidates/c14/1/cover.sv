// Frame error on a frame carrying 8'h5A, with an older word 8'hA5 that was
// already accepted: m_axis_tvalid stays low and m_axis_tdata is unchanged.
module cov_P14 (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata,
  input logic [7:0] data_reg
);

  P14_frame_error_keeps_old_tdata: cover property (@(posedge clk) disable iff (rst)
    frame_error && !m_axis_tvalid && (m_axis_tdata == 8'hA5) && (data_reg == 8'h5A));

endmodule

bind uart_rx cov_P14 u_cov_P14 (.*);
